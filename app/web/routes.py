from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, get_settings
from app.database import SessionLocal, get_db
from app.models import CrawlRun, Keyword, ProductCrawlRun, ProductKeyword, VideoKeyword
from app.services.budget import BudgetGuard
from app.services.crawler import CrawlInProgress, run_crawl
from app.services.mock_seed import seed_mock_data
from app.services.product_budget import ProductBudgetGuard
from app.services.product_crawler import (
    ProductCrawlBlocked,
    ProductCrawlInProgress,
    run_product_crawl,
)
from app.services.product_images import cache_product_image, cached_image_path
from app.services.product_queries import load_product_cards, product_to_dict
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
        "product_mock_mode": settings.product_mock_mode,
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


def _budget_dict(db: Session) -> dict:
    snap = ProductBudgetGuard(db).validate_run()
    return {
        "crawl_enabled": snap.crawl_enabled,
        "mock_mode": snap.mock_mode,
        "has_token": snap.has_token,
        "free_preview_mode": snap.free_preview_mode,
        "preview_used": snap.preview_used,
        "preview_limit": snap.preview_limit,
        "monthly_budget_usd": float(snap.monthly_budget_usd),
        "usable_budget_usd": float(snap.usable_budget_usd),
        "estimated_monthly_cost_usd": float(snap.estimated_monthly_cost_usd),
        "estimated_run_cost_usd": float(snap.estimated_run_cost_usd),
        "remaining_usd": float(snap.remaining_usd),
        "results_per_keyword": snap.results_per_keyword,
        "can_run": snap.can_run,
        "reason": snap.reason,
        "note": "Chi phí là ước tính nội bộ, chưa phải hóa đơn Apify chính thức.",
    }


@router.get("/products")
def products_page(
    request: Request,
    keyword_id: int | None = None,
    only_relevant: int = 0,
    only_new: int = 0,
    only_fast_growth: int = 0,
    min_sold: int | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = "rank_score",
    db: Session = Depends(get_db),
):
    if sort not in ("rank_score", "monthly_sold", "growth"):
        sort = "rank_score"
    cards = load_product_cards(
        db,
        keyword_id=keyword_id,
        only_relevant=bool(only_relevant),
        only_new=bool(only_new),
        only_fast_growth=bool(only_fast_growth),
        min_sold=min_sold,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )
    keywords = db.query(ProductKeyword).order_by(ProductKeyword.id).all()
    budget = _budget_dict(db)
    return templates.TemplateResponse(
        "products.html",
        _common(
            request,
            db,
            {
                "cards": cards,
                "keywords": keywords,
                "keyword_id": keyword_id,
                "only_relevant": only_relevant,
                "only_new": only_new,
                "only_fast_growth": only_fast_growth,
                "min_sold": min_sold,
                "min_price": min_price,
                "max_price": max_price,
                "sort": sort,
                "budget": budget,
            },
        ),
    )


@router.get("/products/keywords")
def product_keywords_page(request: Request, db: Session = Depends(get_db)):
    keywords = db.query(ProductKeyword).order_by(ProductKeyword.id).all()
    budget = _budget_dict(db)
    return templates.TemplateResponse(
        "product_keywords.html",
        _common(request, db, {"keywords": keywords, "budget": budget}),
    )


@router.post("/products/keywords")
def create_product_keyword(
    keyword: str = Form(...),
    vietnamese_meaning: str = Form(""),
    db: Session = Depends(get_db),
):
    word = keyword.strip()
    if not word:
        return _redirect("/products/keywords", error="Từ khóa không được trống.")
    exists = db.query(ProductKeyword).filter(ProductKeyword.keyword == word).one_or_none()
    if exists:
        return _redirect("/products/keywords", error="Từ khóa đã tồn tại.")
    db.add(ProductKeyword(keyword=word, vietnamese_meaning=vietnamese_meaning.strip(), enabled=True))
    db.commit()
    return _redirect("/products/keywords", message="Đã thêm từ khóa sản phẩm.")


@router.post("/products/keywords/{keyword_id}/update")
def update_product_keyword(
    keyword_id: int,
    keyword: str = Form(...),
    vietnamese_meaning: str = Form(""),
    db: Session = Depends(get_db),
):
    row = db.get(ProductKeyword, keyword_id)
    if not row:
        return _redirect("/products/keywords", error="Không tìm thấy từ khóa.")
    row.keyword = keyword.strip()
    row.vietnamese_meaning = vietnamese_meaning.strip()
    row.updated_at = datetime.utcnow()
    db.commit()
    return _redirect("/products/keywords", message="Đã cập nhật từ khóa sản phẩm.")


@router.post("/products/keywords/{keyword_id}/toggle")
def toggle_product_keyword(keyword_id: int, db: Session = Depends(get_db)):
    row = db.get(ProductKeyword, keyword_id)
    if not row:
        return _redirect("/products/keywords", error="Không tìm thấy từ khóa.")
    row.enabled = not row.enabled
    row.updated_at = datetime.utcnow()
    db.commit()
    return _redirect("/products/keywords", message="Đã đổi trạng thái từ khóa sản phẩm.")


@router.post("/products/keywords/{keyword_id}/delete")
def delete_product_keyword(keyword_id: int, db: Session = Depends(get_db)):
    from app.models import ProductKeywordLink

    row = db.get(ProductKeyword, keyword_id)
    if not row:
        return _redirect("/products/keywords", error="Không tìm thấy từ khóa.")
    db.query(ProductKeywordLink).filter(ProductKeywordLink.keyword_id == keyword_id).delete()
    db.delete(row)
    db.commit()
    return _redirect("/products/keywords", message="Đã xóa từ khóa sản phẩm.")


@router.post("/products/keywords/{keyword_id}/crawl")
async def crawl_product_keyword(keyword_id: int, db: Session = Depends(get_db)):
    budget = ProductBudgetGuard(db).validate_run()
    if not budget.can_run:
        return _redirect("/products/keywords", error=budget.reason or "Không thể crawl.")
    try:
        run = await run_product_crawl(db, keyword_id)
    except ProductCrawlInProgress as exc:
        return _redirect("/products/keywords", error=str(exc))
    except ProductCrawlBlocked as exc:
        return _redirect("/products/keywords", error=str(exc))
    if run.status == "error":
        return _redirect("/products/keywords", error=run.error_message or "Crawl lỗi.")
    return _redirect(
        "/products/keywords",
        message=(
            f"Crawl xong: nhận {run.received_count}, chấp nhận {run.accepted_count}, "
            f"mới {run.new_product_count}, ước tính {run.estimated_cost_usd} USD."
        ),
    )


@router.get("/products/runs")
def product_runs_page(request: Request, db: Session = Depends(get_db)):
    runs = (
        db.query(ProductCrawlRun)
        .order_by(ProductCrawlRun.started_at.desc())
        .limit(50)
        .all()
    )
    keywords = {row.id: row for row in db.query(ProductKeyword).all()}
    budget = _budget_dict(db)
    return templates.TemplateResponse(
        "product_runs.html",
        _common(request, db, {"runs": runs, "keywords": keywords, "budget": budget}),
    )


@router.get("/products/{product_id:int}")
def product_detail_page(product_id: int, request: Request, db: Session = Depends(get_db)):
    card = next((item for item in load_product_cards(db) if item.product.id == product_id), None)
    if card is None:
        return RedirectResponse("/products?error=Không+tìm+thấy+sản+phẩm", status_code=303)
    snapshots = sorted(
        card.product.snapshots,
        key=lambda item: (item.captured_at, item.id),
        reverse=True,
    )
    return templates.TemplateResponse(
        "product_detail.html",
        _common(request, db, {"card": card, "snapshots": snapshots}),
    )


@router.get("/products/{product_id:int}/image")
async def product_cached_image(product_id: int, db: Session = Depends(get_db)):
    from app.models import Product

    product = db.get(Product, product_id)
    if product is None:
        return Response(status_code=404)
    path = cached_image_path(product.external_product_id)
    if path is None and product.main_image_url:
        path = await cache_product_image(product.external_product_id, product.main_image_url)
    if path is None or not path.is_file():
        return Response(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=2592000"})


class ProductCrawlBody(BaseModel):
    keyword_id: int | None = None
    keyword: str | None = None


@router.post("/api/products/crawl")
async def api_products_crawl(payload: ProductCrawlBody, db: Session = Depends(get_db)):
    keyword_id = payload.keyword_id
    if keyword_id is None and payload.keyword:
        row = (
            db.query(ProductKeyword)
            .filter(ProductKeyword.keyword == payload.keyword.strip())
            .one_or_none()
        )
        if row is None:
            return {"ok": False, "error": "Không tìm thấy từ khóa."}
        keyword_id = row.id
    try:
        keyword_id = int(keyword_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return {"ok": False, "error": "Thiếu keyword_id hợp lệ."}
    try:
        run = await run_product_crawl(db, keyword_id)
    except ProductCrawlInProgress as exc:
        return {"ok": False, "error": str(exc)}
    except ProductCrawlBlocked as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": run.status == "success",
        "run": {
            "id": run.id,
            "status": run.status,
            "keyword_id": run.keyword_id,
            "received_count": run.received_count,
            "accepted_count": run.accepted_count,
            "rejected_count": run.rejected_count,
            "new_product_count": run.new_product_count,
            "estimated_cost_usd": run.estimated_cost_usd,
            "apify_run_id": run.apify_run_id,
            "error_message": run.error_message,
        },
    }


@router.get("/api/products")
def api_products(
    keyword_id: int | None = None,
    only_relevant: int = 0,
    only_new: int = 0,
    only_fast_growth: int = 0,
    min_sold: int | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = "rank_score",
    db: Session = Depends(get_db),
):
    cards = load_product_cards(
        db,
        keyword_id=keyword_id,
        only_relevant=bool(only_relevant),
        only_new=bool(only_new),
        only_fast_growth=bool(only_fast_growth),
        min_sold=min_sold,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )
    return {"items": [product_to_dict(card) for card in cards], "count": len(cards)}


@router.get("/api/products/runs")
def api_product_runs(db: Session = Depends(get_db)):
    runs = (
        db.query(ProductCrawlRun)
        .order_by(ProductCrawlRun.started_at.desc())
        .limit(50)
        .all()
    )
    return {
        "items": [
            {
                "id": run.id,
                "keyword_id": run.keyword_id,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "requested_limit": run.requested_limit,
                "received_count": run.received_count,
                "normalized_count": run.normalized_count,
                "accepted_count": run.accepted_count,
                "rejected_count": run.rejected_count,
                "new_product_count": run.new_product_count,
                "duplicate_count": run.duplicate_count,
                "estimated_cost_usd": run.estimated_cost_usd,
                "apify_run_id": run.apify_run_id,
                "apify_dataset_id": run.apify_dataset_id,
                "error_message": run.error_message,
            }
            for run in runs
        ]
    }


@router.get("/api/products/budget")
def api_product_budget(db: Session = Depends(get_db)):
    return _budget_dict(db)


@router.get("/api/products/{product_id}")
def api_product_detail(product_id: int, db: Session = Depends(get_db)):
    cards = [c for c in load_product_cards(db) if c.product.id == product_id]
    if not cards:
        return {"ok": False, "error": "Không tìm thấy sản phẩm."}
    return {"ok": True, "item": product_to_dict(cards[0])}
