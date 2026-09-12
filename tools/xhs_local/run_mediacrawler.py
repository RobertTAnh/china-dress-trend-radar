from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tools.xhs_local.local_log import get_logger

logger = get_logger()

SESSION_HINTS = (
    "login",
    "qrcode",
    "qr code",
    "captcha",
    "slide",
    "验证",
    "登录",
    "扫码",
    "cookie",
    "session expired",
)

PERMISSION_HINTS = (
    "没有权限访问",
    "no permission",
    "permission denied",
)


def detect_session_issue(text: str) -> bool:
    lowered = text.lower()
    # Successful-login messages also contain words such as "login" and
    # "cookie". They must not turn an unrelated crawler error into a QR error.
    if "login successful" in lowered or "login success" in lowered:
        return False
    return any(hint in lowered for hint in SESSION_HINTS)


def detect_permission_issue(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in PERMISSION_HINTS)


def patch_mediacrawler_config(root: Path, max_notes: int) -> None:
    config_path = root / "config" / "base_config.py"
    if not config_path.exists():
        logger.warning("Không thấy %s — bỏ qua patch config.", config_path)
        return
    text = config_path.read_text(encoding="utf-8")
    replacements = {
        "ENABLE_GET_COMMENTS": "ENABLE_GET_COMMENTS = False",
        "ENABLE_GET_SUB_COMMENTS": "ENABLE_GET_SUB_COMMENTS = False",
        "ENABLE_GET_MEIDAS": "ENABLE_GET_MEIDAS = False",
        "ENABLE_GET_MEDIAS": "ENABLE_GET_MEDIAS = False",
        "ENABLE_GET_IMAGES": "ENABLE_GET_IMAGES = False",
        "SAVE_LOGIN_STATE": "SAVE_LOGIN_STATE = True",
        "ENABLE_SAVE_LOGIN_STATE": "ENABLE_SAVE_LOGIN_STATE = True",
        "HEADLESS": "HEADLESS = False",
        "CRAWLER_MAX_NOTES_COUNT": f"CRAWLER_MAX_NOTES_COUNT = {max_notes}",
        "CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES": "CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = 0",
    }
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        replaced = False
        for key, new_line in replacements.items():
            if stripped.startswith(key) and "=" in stripped:
                indent = line[: len(line) - len(line.lstrip())]
                lines.append(f"{indent}{new_line}")
                replaced = True
                break
        if not replaced:
            lines.append(line)
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # The popularity sort can be unavailable to some otherwise valid web
    # accounts. General search is the least restrictive mode and is sufficient
    # because this project scores/ranks the returned notes itself.
    xhs_config_path = root / "config" / "xhs_config.py"
    if xhs_config_path.exists():
        xhs_text = xhs_config_path.read_text(encoding="utf-8")
        xhs_lines = []
        for line in xhs_text.splitlines():
            if line.strip().startswith("SORT_TYPE") and "=" in line:
                indent = line[: len(line) - len(line.lstrip())]
                xhs_lines.append(f'{indent}SORT_TYPE = "general"')
            else:
                xhs_lines.append(line)
        xhs_config_path.write_text("\n".join(xhs_lines) + "\n", encoding="utf-8")
    logger.info(
        "Patched MediaCrawler config: comments off, media off, max_notes=%s, sort=general",
        max_notes,
    )


def run_search(root: Path, keyword: str, max_notes: int, python_exe: str, login_type: str = "qrcode") -> int:
    patch_mediacrawler_config(root, max_notes)
    main_py = root / "main.py"
    if not main_py.exists():
        raise FileNotFoundError(f"Không thấy main.py trong {root}")
    cmd = [
        python_exe,
        str(main_py),
        "--platform",
        "xhs",
        "--lt",
        login_type,
        "--type",
        "search",
        "--keywords",
        keyword,
    ]
    logger.info("Chạy MediaCrawler: %s", " ".join(cmd[:-1] + ["[keyword]"]))
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    logger.info("MediaCrawler exit=%s", proc.returncode)
    for line in output.splitlines()[-80:]:
        logger.info("mc: %s", line)
    if proc.returncode != 0 and detect_permission_issue(output):
        logger.error(
            "Đã đăng nhập Xiaohongshu nhưng tài khoản không có quyền dùng tìm kiếm web. "
            "Hãy thử tìm kiếm trực tiếp trên xiaohongshu.com bằng cùng tài khoản; nếu vẫn bị chặn, "
            "cần đổi sang tài khoản khác đã dùng ổn định tại Trung Quốc."
        )
        raise SystemExit(3)
    if proc.returncode != 0 and detect_session_issue(output):
        logger.error(
            "Session Xiaohongshu hết hạn hoặc gặp captcha. "
            "Mở MediaCrawler trên máy này và quét lại QR. Không tự vượt captcha."
        )
        raise SystemExit(2)
    if proc.returncode != 0:
        raise RuntimeError(f"MediaCrawler lỗi exit={proc.returncode}")
    return proc.returncode


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit("Usage: run_mediacrawler.py <root> <keyword> <max_notes>")
    run_search(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.executable)
