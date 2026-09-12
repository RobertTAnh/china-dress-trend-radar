from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import (
    DEFAULT_KEYWORDS,
    DEFAULT_PRODUCT_KEYWORDS,
    DEFAULT_XHS_KEYWORDS,
    LEGACY_KEYWORDS,
    SETTING_KEYS,
)
from app.models import AppSetting, Keyword, ProductKeyword, XhsKeyword

ENV_SETTING_KEYS = {
    "SCHEDULER_ENABLED": "scheduler_enabled",
    "SCHEDULER_HOUR": "scheduler_hour",
    "SCHEDULER_MINUTE": "scheduler_minute",
    "PAGES_PER_KEYWORD": "pages_per_keyword",
    "MAX_REQUESTS_PER_RUN": "max_requests_per_run",
    "MAX_REQUESTS_PER_MONTH": "max_requests_per_month",
    "PRODUCT_CRAWL_ENABLED": "product_crawl_enabled",
    "PRODUCT_MOCK_MODE": "product_mock_mode",
    "PRODUCT_FREE_PREVIEW_MODE": "product_free_preview_mode",
    "PRODUCT_AUTO_SCHEDULE_ENABLED": "product_auto_schedule_enabled",
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
            "apify_actor_id": settings.apify_actor_id,
            "apify_monthly_budget_usd": str(settings.apify_monthly_budget_usd),
            "apify_estimated_price_per_1000_products": str(
                settings.apify_estimated_price_per_1000_products
            ),
            "product_results_per_keyword": str(settings.product_results_per_keyword),
            "product_max_keywords_per_run": str(settings.product_max_keywords_per_run),
            "product_crawl_enabled": str(settings.product_crawl_enabled).lower(),
            "product_free_preview_mode": str(settings.product_free_preview_mode).lower(),
            "product_free_preview_run_limit": str(settings.product_free_preview_run_limit),
            "product_auto_schedule_enabled": str(
                settings.product_auto_schedule_enabled
            ).lower(),
            "product_mock_mode": str(settings.product_mock_mode).lower(),
            "xhs_trend_weight_relevance": "0.35",
            "xhs_trend_weight_collect": "0.30",
            "xhs_trend_weight_like": "0.20",
            "xhs_trend_weight_comment": "0.05",
            "xhs_trend_weight_freshness": "0.10",
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

    # The bulk statistics endpoint costs $0.025 per call. Upgrade only the
    # previous built-in value so a user-customized price remains untouched.
    stats_cost = db.get(AppSetting, "cost_per_stats_usd")
    if stats_cost is not None and stats_cost.value == "0.001":
        stats_cost.value = "0.025"

    # Migrate the original broad ceremonial keyword profile to the narrower
    # Tisora commercial-dress profile without touching user-created keywords.
    for legacy in db.query(Keyword).filter(Keyword.keyword.in_(LEGACY_KEYWORDS)).all():
        legacy.active = False
    existing_keywords = {row.keyword: row for row in db.query(Keyword).all()}
    for word, meaning in DEFAULT_KEYWORDS:
        keyword = existing_keywords.get(word)
        if keyword is None:
            db.add(Keyword(keyword=word, vietnamese_meaning=meaning, active=True))
        else:
            keyword.vietnamese_meaning = meaning

    existing_product_keywords = {
        row.keyword: row for row in db.query(ProductKeyword).all()
    }
    for word, meaning in DEFAULT_PRODUCT_KEYWORDS:
        keyword = existing_product_keywords.get(word)
        if keyword is None:
            db.add(
                ProductKeyword(
                    keyword=word,
                    vietnamese_meaning=meaning,
                    enabled=True,
                )
            )
        else:
            keyword.vietnamese_meaning = meaning

    existing_xhs = {row.keyword: row for row in db.query(XhsKeyword).all()}
    for word, meaning in DEFAULT_XHS_KEYWORDS:
        keyword = existing_xhs.get(word)
        if keyword is None:
            db.add(
                XhsKeyword(
                    keyword=word,
                    vietnamese_meaning=meaning,
                    enabled=True,
                    max_results=30,
                )
            )
        else:
            keyword.vietnamese_meaning = meaning
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
