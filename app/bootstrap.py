from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config import PROJECT_ROOT, get_settings
from app.database import SessionLocal, engine
from app.models import CrawlRun, ProductCrawlRun
from app.services.seed_defaults import seed_defaults

logger = logging.getLogger(__name__)


def _alembic_config() -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def run_migrations() -> None:
    """Always upgrade to Alembic head so new revisions are not skipped."""
    get_settings()
    cfg = _alembic_config()
    try:
        command.upgrade(cfg, "head")
    except Exception:
        logger.exception("Alembic upgrade failed")
        raise


def recover_stale_runs() -> None:
    db = SessionLocal()
    try:
        stale = db.query(CrawlRun).filter(CrawlRun.status == "running").all()
        for run in stale:
            run.status = "error"
            run.error_message = "Ứng dụng khởi động lại khi lần chạy chưa hoàn tất."
            run.finished_at = datetime.utcnow()
        product_stale = (
            db.query(ProductCrawlRun).filter(ProductCrawlRun.status == "running").all()
        )
        for run in product_stale:
            run.status = "error"
            run.error_message = "Ứng dụng khởi động lại khi lần chạy sản phẩm chưa hoàn tất."
            run.finished_at = datetime.utcnow()
        if stale or product_stale:
            db.commit()
    finally:
        db.close()


def bootstrap() -> None:
    Path(PROJECT_ROOT / "data").mkdir(parents=True, exist_ok=True)
    # Ensure engine can connect (creates empty sqlite file if needed).
    inspect(engine)
    run_migrations()
    recover_stale_runs()
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()
