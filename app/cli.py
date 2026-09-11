from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.bootstrap import bootstrap
from app.config import get_settings
from app.database import SessionLocal
from app.logging_utils import configure_logging
from app.services.crawler import run_crawl
from app.services.mock_seed import seed_mock_data


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def cmd_crawl() -> None:
    db = SessionLocal()
    try:
        run = asyncio.run(run_crawl(db))
        print(
            f"Crawl xong: status={run.status} requests={run.request_count} "
            f"videos={run.result_count} mới={run.new_video_count} "
            f"cost_usd={run.estimated_cost_usd}"
        )
        if run.error_message:
            print(f"Cảnh báo: {run.error_message}")
    finally:
        db.close()


def cmd_seed() -> None:
    db = SessionLocal()
    try:
        created = seed_mock_data(db)
        print(f"Đã seed dữ liệu mẫu. Video mới tạo: {created}")
    finally:
        db.close()


def main() -> None:
    _configure_stdio()
    configure_logging(get_settings().log_level)
    bootstrap()
    parser = argparse.ArgumentParser(description="China Dress Trend Radar CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("crawl", help="Chạy crawler một lần")
    sub.add_parser("seed", help="Seed dữ liệu mock")
    args = parser.parse_args()
    if args.command == "crawl":
        cmd_crawl()
    elif args.command == "seed":
        cmd_seed()


if __name__ == "__main__":
    main()
