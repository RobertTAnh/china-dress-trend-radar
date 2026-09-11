from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import DEFAULT_KEYWORDS, SETTING_KEYS
from app.models import AppSetting, Keyword

ENV_SETTING_KEYS = {
    "SCHEDULER_ENABLED": "scheduler_enabled",
    "SCHEDULER_HOUR": "scheduler_hour",
    "SCHEDULER_MINUTE": "scheduler_minute",
    "PAGES_PER_KEYWORD": "pages_per_keyword",
    "MAX_REQUESTS_PER_RUN": "max_requests_per_run",
    "MAX_REQUESTS_PER_MONTH": "max_requests_per_month",
}


def seed_defaults(db: Session) -> None:
    settings = get_settings()
    defaults = dict(SETTING_KEYS)
    defaults.update(
        {
            "usd_vnd_rate": str(settings.usd_vnd_rate),
            "cost_per_search_usd": str(settings.cost_per_search_usd),
            "cost_per_stats_usd": str(settings.cost_per_stats_usd),
            "max_requests_per_run": str(settings.max_requests_per_run),
            "max_requests_per_month": str(settings.max_requests_per_month),
            "pages_per_keyword": str(settings.pages_per_keyword),
            "max_detail_videos_per_run": str(settings.max_detail_videos_per_run),
            "search_sort_type": settings.search_sort_type,
            "search_publish_time": settings.search_publish_time,
            "search_content_type": settings.search_content_type,
            "tikhub_search_endpoint": settings.tikhub_search_endpoint,
            "tikhub_use_fallback_search": str(settings.tikhub_use_fallback_search).lower(),
            "scheduler_enabled": str(settings.scheduler_enabled).lower(),
            "scheduler_hour": str(settings.scheduler_hour),
            "scheduler_minute": str(settings.scheduler_minute),
            "internal_rate_limit_rps": str(settings.internal_rate_limit_rps),
        }
    )
    known = {
        obj.key
        for obj in db.new
        if isinstance(obj, AppSetting)
    }
    known.update(row.key for row in db.query(AppSetting).all())
    for key, value in defaults.items():
        if key in known:
            continue
        db.add(AppSetting(key=key, value=value))
        known.add(key)

    if db.query(Keyword).count() == 0:
        for word, meaning in DEFAULT_KEYWORDS:
            db.add(Keyword(keyword=word, vietnamese_meaning=meaning, active=True))
    db.flush()
    sync_runtime_env(db)
    db.commit()


def sync_runtime_env(db: Session) -> None:
    """Railway/env vars win so the crawler can stay scheduled after redeploy."""
    for env_key, setting_key in ENV_SETTING_KEYS.items():
        value = os.getenv(env_key)
        if value is None or value.strip() == "":
            continue
        normalized = value.strip()
        if env_key == "SCHEDULER_ENABLED":
            normalized = normalized.lower()
        set_setting(db, setting_key, normalized)


def get_setting(db: Session, key: str, default: str | None = None) -> str:
    row = db.get(AppSetting, key)
    if row is None:
        if default is not None:
            return default
        return SETTING_KEYS.get(key, "")
    return row.value


def get_setting_int(db: Session, key: str, default: int) -> int:
    try:
        return int(float(get_setting(db, key, str(default))))
    except (TypeError, ValueError):
        return default


def get_setting_float(db: Session, key: str, default: float) -> float:
    try:
        return float(get_setting(db, key, str(default)))
    except (TypeError, ValueError):
        return default


def get_setting_bool(db: Session, key: str, default: bool = False) -> bool:
    value = get_setting(db, key, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        row = db.query(AppSetting).filter(AppSetting.key == key).one_or_none()
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
