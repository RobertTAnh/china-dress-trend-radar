from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, get_settings
from app.database import SessionLocal, get_db
from app.models import CrawlRun, Keyword, VideoKeyword
from app.services.budget import BudgetGuard
from app.services.crawler import CrawlInProgress, run_crawl
from app.services.mock_seed import seed_mock_data
from app.services.progress import progress_store
from app.services.queries import load_video_cards
from app.services.seed_defaults import (
    get_setting,
    seed_defaults,
    set_setting,
)
from app.web.helpers import (
    dashboard_stats,
    format_date,
    format_datetime,
    format_int,
    format_money_usd,
    format_money_vnd,
    safe_http_url,
)

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "web" / "templates"))
templates.env.filters["vndate"] = format_date
templates.env.filters["vndatetime"] = format_datetime
templates.env.filters["vnint"] = format_int
templates.env.filters["usd"] = format_money_usd
templates.env.filters["vnd"] = format_money_vnd
templates.env.filters["safe_url"] = safe_http_url
templates.env.autoescape = True

router = APIRouter()


def _redirect(path: str, **params) -> RedirectResponse:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{path}?{query}" if query else path
    return RedirectResponse(url, status_code=303)


def _common(request: Request, db: Session, extra: dict | None = None) -> dict:
    settings = get_settings()
    progress = progress_store.get()
    data = {
        "request": request,
        "app_name": settings.app_name,
        "mock_mode": settings.mock_mode,
        "progress": progress,
        "message": request.query_params.get("message"),
        "error": request.query_params.get("error"),
    }
    if extra:
        data.update(extra)
    return data


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    stats = dashboard_stats(db)
    top7 = load_video_cards(db, days=7, trending_only=True, sort="trend_score", limit=8)
    top30 = load_video_cards(db, days=30, trending_only=True, sort="trend_score", limit=8)
    return templates.TemplateResponse(
        "dashboard.html",
        _common(request, db, {"stats": stats, "top7": top7, "top30": top30}),
    )


@router.get("/videos")
def videos_page(
    request: Request,
    days: int = 7,
    keyword_id: int | None = None,
    min_score: float | None = None,
    only_new: int = 0,
    sort: str = "trend_score",
    db: Session = Depends(get_db),
):
    if days not in (7, 30):
        days = 7
    if sort not in ("trend_score", "like_velocity", "published_at"):
        sort = "trend_score"
    cards = load_video_cards(
        db,
        days=days,
        keyword_id=keyword_id,
        min_score=min_score,
        only_new=bool(only_new),
        sort=sort,
        include_needs_review=True,
    )
    keywords = db.query(Keyword).order_by(Keyword.id).all()
    return templates.TemplateResponse(
        "videos.html",
        _common(
            request,
            db,
            {
                "cards": cards,
                "keywords": keywords,
                "days": days,
                "keyword_id": keyword_id,
                "min_score": min_score,
                "only_new": only_new,
                "sort": sort,
            },
        ),
    )


@router.get("/keywords")
def keywords_page(request: Request, db: Session = Depends(get_db)):
    keywords = db.query(Keyword).order_by(Keyword.id).all()
    return templates.TemplateResponse(
        "keywords.html",
        _common(request, db, {"keywords": keywords}),
    )


@router.post("/keywords")
def create_keyword(
    keyword: str = Form(...),
    vietnamese_meaning: str = Form(""),
    db: Session = Depends(get_db),
):
    word = keyword.strip()
    if not word:
        return _redirect("/keywords", error="Từ khóa không được trống.")
    exists = db.query(Keyword).filter(Keyword.keyword == word).one_or_none()
    if exists:
        return _redirect("/keywords", error="Từ khóa đã tồn tại.")
    db.add(Keyword(keyword=word, vietnamese_meaning=vietnamese_meaning.strip(), active=True))
    db.commit()
    return _redirect("/keywords", message="Đã thêm từ khóa.")


@router.post("/keywords/{keyword_id}/update")
def update_keyword(
    keyword_id: int,
    keyword: str = Form(...),
    vietnamese_meaning: str = Form(""),
    db: Session = Depends(get_db),
):
    row = db.get(Keyword, keyword_id)
    if not row:
        return _redirect("/keywords", error="Không tìm thấy từ khóa.")
    row.keyword = keyword.strip()
    row.vietnamese_meaning = vietnamese_meaning.strip()
    db.commit()
    return _redirect("/keywords", message="Đã cập nhật từ khóa.")


@router.post("/keywords/{keyword_id}/toggle")
def toggle_keyword(keyword_id: int, db: Session = Depends(get_db)):
    row = db.get(Keyword, keyword_id)
    if not row:
        return _redirect("/keywords", error="Không tìm thấy từ khóa.")
    row.active = not row.active
    db.commit()
    return _redirect("/keywords", message="Đã đổi trạng thái từ khóa.")


@router.post("/keywords/{keyword_id}/delete")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db)):
    row = db.get(Keyword, keyword_id)
    if not row:
        return _redirect("/keywords", error="Không tìm thấy từ khóa.")
    db.query(VideoKeyword).filter(VideoKeyword.keyword_id == keyword_id).delete()
    db.delete(row)
    db.commit()
    return _redirect("/keywords", message="Đã xóa từ khóa.")


@router.get("/runs")
def runs_page(request: Request, db: Session = Depends(get_db)):
    runs = db.query(CrawlRun).order_by(CrawlRun.started_at.desc()).limit(50).all()
    return templates.TemplateResponse("runs.html", _common(request, db, {"runs": runs}))


@router.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db)):
    seed_defaults(db)
    keys = [
        "usd_vnd_rate",
        "cost_per_search_usd",
        "cost_per_stats_usd",
        "max_requests_per_run",
        "max_requests_per_month",
        "pages_per_keyword",
        "max_detail_videos_per_run",
        "search_sort_type",
        "search_publish_time",
        "search_content_type",
        "tikhub_search_endpoint",
        "tikhub_use_fallback_search",
        "scheduler_enabled",
        "scheduler_hour",
        "scheduler_minute",
        "internal_rate_limit_rps",
    ]
    values = {key: get_setting(db, key) for key in keys}
    budget = BudgetGuard(db).snapshot()
    return templates.TemplateResponse(
        "settings.html",
        _common(request, db, {"values": values, "budget": budget}),
    )


@router.post("/settings")
def save_settings(
    request: Request,
    usd_vnd_rate: str = Form(...),
    cost_per_search_usd: str = Form(...),
    cost_per_stats_usd: str = Form(...),
    max_requests_per_run: str = Form(...),
    max_requests_per_month: str = Form(...),
    pages_per_keyword: str = Form(...),
    max_detail_videos_per_run: str = Form(...),
    search_sort_type: str = Form(...),
    search_publish_time: str = Form(...),
    search_content_type: str = Form(...),
    tikhub_search_endpoint: str = Form(...),
    tikhub_use_fallback_search: str = Form("false"),
    scheduler_enabled: str = Form("false"),
    scheduler_hour: str = Form("9"),
    scheduler_minute: str = Form("0"),
    internal_rate_limit_rps: str = Form("2.0"),
    db: Session = Depends(get_db),
):
    mapping = {
        "usd_vnd_rate": usd_vnd_rate,
        "cost_per_search_usd": cost_per_search_usd,
        "cost_per_stats_usd": cost_per_stats_usd,
        "max_requests_per_run": max_requests_per_run,
        "max_requests_per_month": max_requests_per_month,
        "pages_per_keyword": pages_per_keyword,
        "max_detail_videos_per_run": max_detail_videos_per_run,
        "search_sort_type": search_sort_type,
        "search_publish_time": search_publish_time,
        "search_content_type": search_content_type,
        "tikhub_search_endpoint": tikhub_search_endpoint,
        "tikhub_use_fallback_search": tikhub_use_fallback_search,
        "scheduler_enabled": scheduler_enabled,
        "scheduler_hour": scheduler_hour,
        "scheduler_minute": scheduler_minute,
        "internal_rate_limit_rps": internal_rate_limit_rps,
    }
    for key, value in mapping.items():
        set_setting(db, key, value.strip())
    db.commit()
    try:
        from app.scheduler import start_scheduler

        start_scheduler()
    except Exception:
        logger.exception("Could not restart scheduler after settings save")
    return _redirect("/settings", message="Đã lưu cấu hình.")


@router.post("/crawl/start")
async def crawl_start(db: Session = Depends(get_db)):
    progress = progress_store.get()
    if progress.running:
        return _redirect("/", error="Đang có một lần thu thập chạy.")
    try:
        asyncio.create_task(_crawl_background())
    except CrawlInProgress:
        return _redirect("/", error="Đang có một lần thu thập chạy.")
    return _redirect("/", message="Đã bắt đầu thu thập.")


async def _crawl_background() -> None:
    db = SessionLocal()
    try:
        await run_crawl(db)
    except CrawlInProgress:
        logger.warning("Crawl already running")
    except Exception:
        logger.exception("Background crawl failed")
    finally:
        db.close()


@router.post("/seed")
def seed_now(db: Session = Depends(get_db)):
    created = seed_mock_data(db)
    return _redirect("/", message=f"Đã seed dữ liệu mẫu. Video mới: {created}.")


@router.get("/api/health")
def health():
    return {"ok": True, "app": "China Dress Trend Radar"}


@router.get("/api/crawl/status")
def crawl_status():
    return progress_store.get().as_dict()
