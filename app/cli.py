from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.bootstrap import bootstrap
from app.config import get_settings
from app.database import SessionLocal
from app.logging_utils import configure_logging
from app.models import ProductKeyword
from app.services.crawler import run_crawl
from app.services.mock_seed import seed_mock_data
from app.services.product_crawler import ProductCrawlBlocked, ProductCrawlInProgress, run_product_crawl
from app.services.seed_defaults import seed_defaults


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


def cmd_product_seed() -> None:
    db = SessionLocal()
    try:
        seed_defaults(db)
        count = db.query(ProductKeyword).count()
        print(f"Đã seed từ khóa sản phẩm. Tổng hiện có: {count}")
    finally:
        db.close()


def cmd_product_crawl(keyword_id: int) -> None:
    db = SessionLocal()
    try:
        run = asyncio.run(run_product_crawl(db, keyword_id))
        print(
            f"Product crawl: status={run.status} received={run.received_count} "
            f"accepted={run.accepted_count} rejected={run.rejected_count} "
            f"new={run.new_product_count} cost_usd={run.estimated_cost_usd}"
        )
        if run.error_message:
            print(f"Cảnh báo: {run.error_message}")
    except (ProductCrawlBlocked, ProductCrawlInProgress) as exc:
        print(f"Không chạy được: {exc}")
        raise SystemExit(1) from exc
    finally:
        db.close()


def main() -> None:
    _configure_stdio()
    configure_logging(get_settings().log_level)
    bootstrap()
    parser = argparse.ArgumentParser(description="China Dress Trend Radar CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("crawl", help="Chạy crawler video một lần")
    sub.add_parser("seed", help="Seed dữ liệu mock video")
    sub.add_parser("product-seed", help="Seed từ khóa sản phẩm mặc định")
    product_crawl = sub.add_parser("product-crawl", help="Crawl một từ khóa sản phẩm")
    product_crawl.add_argument("--keyword-id", type=int, required=True)
    args = parser.parse_args()
    if args.command == "crawl":
        cmd_crawl()
    elif args.command == "seed":
        cmd_seed()
    elif args.command == "product-seed":
        cmd_product_seed()
    elif args.command == "product-crawl":
        cmd_product_crawl(args.keyword_id)


if __name__ == "__main__":
    main()
