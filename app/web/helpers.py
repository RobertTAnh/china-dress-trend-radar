from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import CrawlRun, Video
from app.services.budget import monthly_request_count
from app.services.seed_defaults import get_setting_float, get_setting_int


def format_int(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", ".")


def format_money_usd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.4f}".rstrip("0").rstrip(".") + " USD"


def format_money_vnd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{int(round(value)):,}".replace(",", ".") + " ₫"


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d/%m/%Y %H:%M")


def format_date(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d/%m/%Y")


def safe_http_url(url: str | None) -> str:
    if not url:
        return ""
    candidate = url.strip()
    if candidate.startswith(("https://", "http://")):
        return candidate
    return ""


def dashboard_stats(db: Session) -> dict:
    total_videos = db.query(func.count(Video.id)).scalar() or 0
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_videos = (
        db.query(func.count(Video.id)).filter(Video.first_seen_at >= week_ago).scalar() or 0
    )
    month_requests = monthly_request_count(db)
    last_run = db.query(CrawlRun).order_by(CrawlRun.started_at.desc()).first()
    usd_rate = get_setting_float(db, "usd_vnd_rate", 26000)
    month_cost = 0.0
    start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Approximate month cost from crawl_runs in current calendar month UTC; display uses stored USD.
    month_cost = (
        db.query(func.coalesce(func.sum(CrawlRun.estimated_cost_usd), 0.0))
        .filter(CrawlRun.started_at >= start)
        .scalar()
        or 0.0
    )
    return {
        "total_videos": total_videos,
        "new_videos": new_videos,
        "month_requests": month_requests,
        "max_month": get_setting_int(db, "max_requests_per_month", 400),
        "max_run": get_setting_int(db, "max_requests_per_run", 35),
        "month_cost_usd": float(month_cost),
        "month_cost_vnd": float(month_cost) * usd_rate,
        "usd_vnd_rate": usd_rate,
        "last_run": last_run,
        "within_budget": month_requests < get_setting_int(db, "max_requests_per_month", 400),
    }
