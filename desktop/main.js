const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const https = require("https");
const net = require("net");
const path = require("path");
const { URL } = require("url");

const BACKEND_HOST = "127.0.0.1";
const STARTUP_TIMEOUT_MS = 45000;
const DEFAULT_RAILWAY_URL = "https://web-production-f29ae8.up.railway.app";

let mainWindow = null;
let backendProcess = null;
let backendPort = 17800;
let shuttingDown = false;
let activeOrigin = DEFAULT_RAILWAY_URL;
let currentMode = "railway";

function projectRoot() {
  if (app.isPackaged) {
    return process.resourcesPath;
  }
  return path.join(__dirname, "..");
}

function loadDesktopConfig() {
  const candidates = [
    path.join(__dirname, "config.json"),
    path.join(projectRoot(), "desktop", "config.json"),
  ];
  let fileConfig = {};
  for (const file of candidates) {
    if (!fs.existsSync(file)) continue;
    try {
      fileConfig = JSON.parse(fs.readFileSync(file, "utf8"));
      break;
    } catch (_error) {
      fileConfig = {};
    }
  }
  const envMode = (process.env.DESKTOP_MODE || "").trim().toLowerCase();
  const envUrl = (process.env.RAILWAY_APP_URL || process.env.DESKTOP_REMOTE_URL || "").trim();
  const mode = envMode || fileConfig.mode || "railway";
  const railwayUrl = (envUrl || fileConfig.railwayUrl || DEFAULT_RAILWAY_URL).replace(/\/$/, "");
  return {
    mode: mode === "local" ? "local" : "railway",
    railwayUrl,
    localFallback: fileConfig.localFallback !== false,
  };
}

function pythonCandidates(root) {
  return [
    process.env.CHINA_DRESS_PYTHON,
    path.join(root, ".venv", "Scripts", "python.exe"),
    path.join(root, ".venv", "bin", "python"),
    path.join(process.cwd(), ".venv", "Scripts", "python.exe"),
    path.join(path.dirname(process.execPath), ".venv", "Scripts", "python.exe"),
    path.join(path.dirname(app.getPath("exe")), ".venv", "Scripts", "python.exe"),
  ].filter(Boolean);
}

function resolvePython(root) {
  for (const candidate of pythonCandidates(root)) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, BACKEND_HOST, () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 17800;
      server.close((error) => {
        if (error) reject(error);
        else resolve(port);
      });
    });
    server.on("error", reject);
  });
}

function waitForUrl(url, timeoutMs) {
  const started = Date.now();
  const target = new URL(url);
  const client = target.protocol === "https:" ? https : http;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const request = client.get(
        {
          protocol: target.protocol,
          hostname: target.hostname,
          port: target.port || (target.protocol === "https:" ? 443 : 80),
          path: target.pathname + target.search,
          timeout: 2500,
        },
        (response) => {
          response.resume();
          if (response.statusCode && response.statusCode < 500) {
            resolve();
            return;
          }
          retry();
        }
      );
      request.on("error", retry);
      request.on("timeout", () => {
        request.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error("Máy chủ không sẵn sàng trong thời gian chờ."));
        return;
      }
      setTimeout(attempt, 400);
    };
    attempt();
  });
}

function waitForHealth(port, timeoutMs) {
  return waitForUrl(`http://${BACKEND_HOST}:${port}/api/health`, timeoutMs);
}

function stopBackend() {
  if (!backendProcess || backendProcess.killed) {
    backendProcess = null;
    return;
  }
  const pid = backendProcess.pid;
  backendProcess = null;
  if (!pid) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { windowsHide: true });
    return;
  }
  try {
    process.kill(pid, "SIGTERM");
  } catch (_error) {
    // already exited
  }
}

function showError(message, detail) {
  const errorUrl =
    "file://" +
    path.join(__dirname, "error.html") +
    "?message=" +
    encodeURIComponent(message) +
    "&detail=" +
    encodeURIComponent(detail || "");
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(errorUrl);
  }
  dialog.showErrorBox("China Dress Trend Radar", `${message}\n\n${detail || ""}`);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#121018",
    title: "China Dress Trend Radar",
    autoHideMenuBar: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.loadFile(path.join(__dirname, "splash.html"));
  buildMenu();
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function serverOrigin() {
  return activeOrigin;
}

function isAppUrl(url) {
  return url.startsWith(serverOrigin()) || url.startsWith("file://");
}

function attachNavigationGuards() {
  if (!mainWindow) return;
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!isAppUrl(url)) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!isAppUrl(url)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
}

function buildMenu() {
  const origin = serverOrigin();
  const config = loadDesktopConfig();
  const template = [
    {
      label: "Tệp",
      submenu: [
        {
          label: "Tải lại",
          accelerator: "CmdOrCtrl+R",
          click: () => mainWindow && mainWindow.reload(),
        },
        { type: "separator" },
        { label: "Thoát", role: "quit" },
      ],
    },
    {
      label: "Nguồn dữ liệu",
      submenu: [
        {
          label: "Railway (cloud)",
          type: "radio",
          checked: currentMode === "railway",
          click: () => switchMode("railway"),
        },
        {
          label: "Local (máy này)",
          type: "radio",
          checked: currentMode === "local",
          click: () => switchMode("local"),
        },
        { type: "separator" },
        {
          label: "Mở Railway trên trình duyệt",
          click: () => shell.openExternal(config.railwayUrl),
        },
      ],
    },
    {
      label: "Điều hướng",
      submenu: [
        { label: "Tổng quan", click: () => mainWindow && mainWindow.loadURL(`${origin}/`) },
        { label: "Video", click: () => mainWindow && mainWindow.loadURL(`${origin}/videos`) },
        { label: "Từ khóa", click: () => mainWindow && mainWindow.loadURL(`${origin}/keywords`) },
        { label: "Lần chạy", click: () => mainWindow && mainWindow.loadURL(`${origin}/runs`) },
        { label: "Cài đặt", click: () => mainWindow && mainWindow.loadURL(`${origin}/settings`) },
      ],
    },
    {
      label: "Xem",
      submenu: [
        { label: "Phóng to", role: "zoomin" },
        { label: "Thu nhỏ", role: "zoomout" },
        { label: "Cỡ chữ mặc định", role: "resetzoom" },
        { type: "separator" },
        { label: "Toàn màn hình", role: "togglefullscreen" },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function startBackend() {
  const root = projectRoot();
  const python = resolvePython(root);
  if (!python) {
    throw new Error(
      "Không tìm thấy .venv\\Scripts\\python.exe.\nHãy chạy: py -3.11 -m venv .venv rồi pip install -r requirements.txt"
    );
  }
  backendPort = await getFreePort();
  const env = {
    ...process.env,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
    APP_HOST: BACKEND_HOST,
    APP_PORT: String(backendPort),
  };
  backendProcess = spawn(
    python,
    ["-m", "uvicorn", "app.main:app", "--host", BACKEND_HOST, "--port", String(backendPort)],
    {
      cwd: fs.existsSync(path.join(root, "app")) ? root : process.cwd(),
      env,
      windowsHide: true,
    }
  );
  let stderr = "";
  backendProcess.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
    if (stderr.length > 4000) stderr = stderr.slice(-4000);
  });
  backendProcess.on("exit", (code) => {
    if (!shuttingDown && code && code !== 0 && mainWindow && !mainWindow.isDestroyed()) {
      showError("Máy chủ Python đã dừng.", stderr.slice(-1500) || `Mã thoát: ${code}`);
    }
  });
  await waitForHealth(backendPort, STARTUP_TIMEOUT_MS);
  return stderr;
}

async function connectRailway(railwayUrl) {
  activeOrigin = railwayUrl.replace(/\/$/, "");
  currentMode = "railway";
  await waitForUrl(`${activeOrigin}/api/health`, STARTUP_TIMEOUT_MS);
}

async function connectLocal() {
  stopBackend();
  await startBackend();
  activeOrigin = `http://${BACKEND_HOST}:${backendPort}`;
  currentMode = "local";
}

async function loadActiveApp() {
  buildMenu();
  attachNavigationGuards();
  if (mainWindow && !mainWindow.isDestroyed()) {
    await mainWindow.loadURL(`${serverOrigin()}/`);
    mainWindow.setTitle(
      currentMode === "railway"
        ? "China Dress Trend Radar · Railway"
        : "China Dress Trend Radar · Local"
    );
  }
}

async function switchMode(mode) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const config = loadDesktopConfig();
  mainWindow.loadFile(path.join(__dirname, "splash.html"));
  try {
    if (mode === "railway") {
      stopBackend();
      await connectRailway(config.railwayUrl);
    } else {
      await connectLocal();
    }
    await loadActiveApp();
  } catch (error) {
    showError(
      mode === "railway"
        ? "Không kết nối được Railway."
        : "Không khởi động được chế độ local.",
      error && error.message ? error.message : String(error)
    );
  }
}

async function boot() {
  createWindow();
  const config = loadDesktopConfig();
  try {
    if (config.mode === "railway") {
      try {
        await connectRailway(config.railwayUrl);
      } catch (error) {
        if (!config.localFallback) throw error;
        dialog.showMessageBoxSync({
          type: "warning",
          title: "Railway chưa sẵn sàng",
          message: "Không kết nối được Railway. Tạm chuyển sang chế độ Local trên máy này.",
          detail: error && error.message ? error.message : String(error),
        });
        await connectLocal();
      }
    } else {
      await connectLocal();
    }
    await loadActiveApp();
  } catch (error) {
    showError(
      "Không khởi động được China Dress Trend Radar.",
      error && error.message ? error.message : String(error)
    );
  }
}

app.whenReady().then(boot);

app.on("window-all-closed", () => {
  shuttingDown = true;
  stopBackend();
  app.quit();
});

app.on("before-quit", () => {
  shuttingDown = true;
  stopBackend();
});

process.on("exit", stopBackend);
