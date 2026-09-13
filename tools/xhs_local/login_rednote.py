from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.xhs_local.run_mediacrawler import run_search
from tools.xhs_local.run_week import CONFIG_PATH, resolve_mediacrawler_python


def report(config: dict, **fields) -> None:
    job_id = (os.getenv("XHS_REMOTE_JOB_ID") or "").strip()
    url = str(config.get("railway_url") or "").rstrip("/")
    token = str(config.get("ingest_token") or "").strip()
    if job_id and url and token:
        with httpx.Client(timeout=20.0) as client:
            client.post(
                url + "/api/xhs/crawl/progress",
                headers={"Authorization": f"Bearer {token}"},
                json={"job_id": job_id, **fields},
            ).raise_for_status()


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    root = Path(config.get("mediacrawler_path") or r"C:\tools\MediaCrawler")
    python_exe = resolve_mediacrawler_python(root, str(config.get("mediacrawler_python") or ""))
    report(
        config,
        status="running",
        stage="waiting_login",
        message="Chrome đã mở · hãy quét QR đăng nhập trong 2 phút",
        error=None,
    )
    run_search(
        root,
        "连衣裙",
        1,
        str(python_exe),
        international=bool(config.get("xhs_international", True)),
        headless=False,
    )
    report(
        config,
        status="completed",
        stage="login_completed",
        message="Đăng nhập RedNote thành công · bạn có thể bấm Tìm ngay",
        error=None,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    main()
