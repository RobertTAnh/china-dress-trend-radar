from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.xhs_local.local_log import get_logger  # noqa: E402

logger = get_logger()
PROCESSED = PROJECT_ROOT / "data" / "xhs_processed"


def upload_file(path: Path, railway_url: str, token: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    url = railway_url.rstrip("/") + "/api/xhs/ingest"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    logger.info("Uploading %s to %s client_run_id=%s", path.name, url, payload.get("client_run_id"))
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
    body_preview = response.text[:500]
    logger.info("Upload status=%s body=%s", response.status_code, body_preview)
    if response.status_code >= 400:
        raise RuntimeError(f"Upload thất bại HTTP {response.status_code}")
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "Upload không thành công")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    dest = PROCESSED / path.name
    shutil.move(str(path), dest)
    logger.info(
        "Upload OK received=%s accepted=%s rejected=%s new=%s moved=%s",
        data.get("received_count"),
        data.get("accepted_count"),
        data.get("rejected_count"),
        data.get("new_post_count"),
        dest,
    )
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload JSON Xiaohongshu lên Railway")
    parser.add_argument("--file", required=True)
    parser.add_argument("--railway-url", default=os.getenv("XHS_RAILWAY_URL", ""))
    parser.add_argument("--token", default=os.getenv("XHS_INGEST_TOKEN", ""))
    args = parser.parse_args()
    if not args.railway_url or not args.token:
        raise SystemExit("Thiếu XHS_RAILWAY_URL hoặc XHS_INGEST_TOKEN.")
    upload_file(Path(args.file), args.railway_url, args.token)


if __name__ == "__main__":
    main()
