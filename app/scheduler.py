from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.services.crawler import CrawlInProgress, run_crawl
from app.services.seed_defaults import get_setting_bool, get_setting_int

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def scheduled_crawl() -> None:
    db: Session = SessionLocal()
    try:
        if not get_setting_bool(db, "scheduler_enabled", get_settings().scheduler_enabled):
            logger.info("Scheduler tick skipped because scheduler_enabled=false")
            return
        await run_crawl(db)
    except CrawlInProgress:
        logger.warning("Scheduled crawl skipped: another run is active")
    except Exception:
        logger.exception("Scheduled crawl failed")
    finally:
        db.close()


def start_scheduler() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        hour = get_setting_int(db, "scheduler_hour", settings.scheduler_hour)
        minute = get_setting_int(db, "scheduler_minute", settings.scheduler_minute)
        enabled = get_setting_bool(db, "scheduler_enabled", settings.scheduler_enabled)
    finally:
        db.close()
    if scheduler.running:
        scheduler.remove_all_jobs()
    else:
        scheduler.configure(timezone=settings.scheduler_timezone)
        scheduler.start()
    scheduler.add_job(
        scheduled_crawl,
        CronTrigger(
            day_of_week="mon,wed,fri",
            hour=hour,
            minute=minute,
            timezone=settings.scheduler_timezone,
        ),
        id="dress_trend_crawl",
        replace_existing=True,
    )
    logger.info(
        "Scheduler started timezone=%s enabled=%s hour=%s minute=%s",
        settings.scheduler_timezone,
        enabled,
        hour,
        minute,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
