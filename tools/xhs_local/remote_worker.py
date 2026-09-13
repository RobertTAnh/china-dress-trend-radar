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


def report(railway_url: str, headers: dict, payload: dict) -> None:
    with httpx.Client(timeout=20.0) as client:
        client.post(
            railway_url + "/api/xhs/crawl/progress", headers=headers, json=payload
        ).raise_for_status()


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
    action = str(job.get("action") or "crawl")
    script = "login_rednote.py" if action == "login" else "run_week.py"
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / script)],
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    if result.returncode != 0:
        needs_login = result.returncode == 2
        message = "Cần đăng nhập RedNote trên máy tính" if needs_login else "Crawler local gặp lỗi"
        payload = {
            "job_id": job_id,
            "status": "needs_login" if needs_login else "failed",
            "stage": "needs_login" if needs_login else "failed",
            "message": message,
            "error": f"Mã thoát {result.returncode}",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            report(railway_url, headers, payload)
        except Exception:
            pass
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
