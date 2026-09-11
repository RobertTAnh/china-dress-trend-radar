from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.config import PROJECT_ROOT, get_settings
from app.database import Base, SessionLocal, engine
from app.models import CrawlRun
from app.services.seed_defaults import seed_defaults

logger = logging.getLogger(__name__)


def _alembic_config() -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def run_migrations() -> None:
    get_settings()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    cfg = _alembic_config()
    if "keywords" not in tables:
        try:
            command.upgrade(cfg, "head")
        except Exception:
            logger.exception("Alembic migration failed, falling back to create_all")
            Base.metadata.create_all(bind=engine)
    else:
        Base.metadata.create_all(bind=engine)
        try:
            with engine.connect() as conn:
                if "alembic_version" not in inspect(engine).get_table_names():
                    command.stamp(cfg, "head")
                else:
                    rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
                    if not rows:
                        command.stamp(cfg, "head")
        except Exception:
            logger.warning("Could not stamp Alembic version", exc_info=True)


def recover_stale_runs() -> None:
    db = SessionLocal()
    try:
        stale = db.query(CrawlRun).filter(CrawlRun.status == "running").all()
        for run in stale:
            run.status = "error"
            run.error_message = "Ứng dụng khởi động lại khi lần chạy chưa hoàn tất."
            run.finished_at = datetime.utcnow()
        if stale:
            db.commit()
    finally:
        db.close()


def bootstrap() -> None:
    Path(PROJECT_ROOT / "data").mkdir(parents=True, exist_ok=True)
    run_migrations()
    recover_stale_runs()
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()
