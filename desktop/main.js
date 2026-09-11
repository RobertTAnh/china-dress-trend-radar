const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");

const BACKEND_HOST = "127.0.0.1";
const STARTUP_TIMEOUT_MS = 45000;

let mainWindow = null;
let backendProcess = null;
let backendPort = 17800;
let shuttingDown = false;

function projectRoot() {
  if (app.isPackaged) {
    return process.resourcesPath;
  }
  return path.join(__dirname, "..");
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

function waitForHealth(port, timeoutMs) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const request = http.get(
        { host: BACKEND_HOST, port, path: "/api/health", timeout: 1500 },
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
        reject(new Error("Backend không sẵn sàng trong thời gian chờ."));
        return;
      }
      setTimeout(attempt, 350);
    };
    attempt();
  });
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
  return `http://${BACKEND_HOST}:${backendPort}`;
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

async function boot() {
  createWindow();
  try {
    await startBackend();
    buildMenu();
    attachNavigationGuards();
    if (mainWindow && !mainWindow.isDestroyed()) {
      await mainWindow.loadURL(`${serverOrigin()}/`);
    }
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
