from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    railway_url = str(config.get("railway_url") or "").rstrip("/")
    token = str(config.get("ingest_token") or "").strip()
    if not railway_url or not token:
        return 2
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=20.0) as client:
        response = client.post(railway_url + "/api/xhs/crawl/claim", headers=headers)
        response.raise_for_status()
        job = response.json().get("job")
    if not job:
        return 0

    job_id = str(job["job_id"])
    env = os.environ.copy()
    env["XHS_REMOTE_JOB_ID"] = job_id
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "run_week.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    if result.returncode != 0:
        message = "Đã dừng vì captcha/QR" if result.returncode == 2 else "Crawler local gặp lỗi"
        payload = {
            "job_id": job_id,
            "status": "failed",
            "stage": "failed",
            "message": message,
            "error": f"Mã thoát {result.returncode}",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                client.post(
                    railway_url + "/api/xhs/crawl/progress",
                    headers=headers,
                    json=payload,
                ).raise_for_status()
        except Exception:
            pass
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
