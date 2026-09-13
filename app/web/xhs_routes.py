from __future__ import annotations

import hmac
import logging
from datetime import datetime
from uuid import uuid4
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, get_settings
from app.database import get_db
from app.logging_utils import redact_secrets
from app.models import XhsCrawlRun, XhsKeyword, XhsKeywordLink, XhsRemoteJob
from app.services.xhs_ingest import ingest_xhs_payload
from app.services.xhs_queries import load_xhs_cards, xhs_card_to_dict
from app.web.helpers import (
    format_date,
    format_datetime,
    format_int,
    format_money_usd,
    format_money_vnd,
    safe_http_url,
)
from app.web.routes import _common
from app.xhs.schemas import XhsIngestPayload

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


def _optional_int(value: str | int | None, *, minimum: int = 0) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= minimum else None


def _default_remote_state() -> dict:
    return {
        "job_id": None,
        "status": "idle",
        "stage": "idle",
        "message": "Sẵn sàng tìm kiếm",
        "keyword": None,
        "keyword_index": 0,
        "keyword_total": 8,
        "accepted_count": 0,
        "action": "crawl",
        "updated_at": datetime.utcnow().isoformat(),
    }


def _get_remote_state(db: Session) -> dict:
    row = db.query(XhsRemoteJob).order_by(XhsRemoteJob.created_at.desc(), XhsRemoteJob.id.desc()).first()
    if row is None or not isinstance(row.state_json, dict):
        return _default_remote_state()
    return dict(row.state_json)


def _save_remote_state(db: Session, state: dict) -> None:
    state["updated_at"] = datetime.utcnow().isoformat()
    row = db.query(XhsRemoteJob).filter(XhsRemoteJob.job_id == state.get("job_id")).one_or_none()
    if row is None:
        row = XhsRemoteJob(job_id=state["job_id"], status=state["status"], state_json=dict(state))
        db.add(row)
    else:
        row.status = state["status"]
        row.state_json = dict(state)
        row.updated_at = datetime.utcnow()
    db.commit()


def _redirect(path: str, **params) -> RedirectResponse:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{path}?{query}" if query else path
    return RedirectResponse(url, status_code=303)


def _check_ingest_token(request: Request) -> str | None:
    settings = get_settings()
    expected = (settings.xhs_ingest_token or "").strip()
    header = request.headers.get("Authorization") or ""
    provided = ""
    if header.lower().startswith("bearer "):
        provided = header[7:].strip()
    if not expected:
        return "Thiếu XHS_INGEST_TOKEN trên server."
    if not provided or not hmac.compare_digest(provided, expected):
        logger.warning("XHS ingest rejected: token sai hoặc thiếu.")
        return "Token ingest không hợp lệ."
    return None


@router.get("/xhs")
def xhs_page(
    request: Request,
    days: int = 7,
    keyword_id: str | None = None,
    only_relevant: int = 0,
    min_collect: str | None = None,
    min_like: str | None = None,
    sort: str = "trend_score",
    db: Session = Depends(get_db),
):
    if days not in (0, 7, 30):
        days = 7
    if sort not in ("trend_score", "collect", "published_at"):
        sort = "trend_score"
    resolved_keyword_id = _optional_int(keyword_id, minimum=1)
    resolved_min_collect = _optional_int(min_collect)
    resolved_min_like = _optional_int(min_like)
    cards = load_xhs_cards(
        db,
        days=days,
        keyword_id=resolved_keyword_id,
        only_relevant=bool(only_relevant),
        min_collect=resolved_min_collect,
        min_like=resolved_min_like,
        sort=sort,
    )
    keywords = db.query(XhsKeyword).order_by(XhsKeyword.id).all()
    return templates.TemplateResponse(
        "xhs.html",
        _common(
            request,
            db,
            {
                "cards": cards,
                "keywords": keywords,
                "days": days,
                "keyword_id": resolved_keyword_id,
                "only_relevant": only_relevant,
                "min_collect": resolved_min_collect,
                "min_like": resolved_min_like,
                "sort": sort,
                "xhs_crawl": _get_remote_state(db),
            },
        ),
    )


@router.get("/xhs/keywords")
def xhs_keywords_page(request: Request, db: Session = Depends(get_db)):
    keywords = db.query(XhsKeyword).order_by(XhsKeyword.id).all()
    return templates.TemplateResponse(
        "xhs_keywords.html",
        _common(request, db, {"keywords": keywords}),
    )


@router.post("/xhs/keywords")
def create_xhs_keyword(
    keyword: str = Form(...),
    vietnamese_meaning: str = Form(""),
    max_results: int = Form(30),
    db: Session = Depends(get_db),
):
    word = keyword.strip()
    if not word:
        return _redirect("/xhs/keywords", error="Từ khóa không được trống.")
    exists = db.query(XhsKeyword).filter(XhsKeyword.keyword == word).one_or_none()
    if exists:
        return _redirect("/xhs/keywords", error="Từ khóa đã tồn tại.")
    limit = 30 if int(max_results) >= 30 else 20
    db.add(
        XhsKeyword(
            keyword=word,
            vietnamese_meaning=vietnamese_meaning.strip(),
            enabled=True,
            max_results=limit,
        )
    )
    db.commit()
    return _redirect("/xhs/keywords", message="Đã thêm từ khóa Xiaohongshu.")


@router.post("/xhs/keywords/{keyword_id}/update")
def update_xhs_keyword(
    keyword_id: int,
    keyword: str = Form(...),
    vietnamese_meaning: str = Form(""),
    max_results: int = Form(30),
    db: Session = Depends(get_db),
):
    row = db.get(XhsKeyword, keyword_id)
    if not row:
        return _redirect("/xhs/keywords", error="Không tìm thấy từ khóa.")
    word = keyword.strip()
    if not word:
        return _redirect("/xhs/keywords", error="Từ khóa không được trống.")
    duplicate = (
        db.query(XhsKeyword)
        .filter(XhsKeyword.keyword == word, XhsKeyword.id != keyword_id)
        .one_or_none()
    )
    if duplicate:
        return _redirect("/xhs/keywords", error="Từ khóa đã tồn tại.")
    row.keyword = word
    row.vietnamese_meaning = vietnamese_meaning.strip()
    row.max_results = 30 if int(max_results) >= 30 else 20
    row.updated_at = datetime.utcnow()
    db.commit()
    return _redirect("/xhs/keywords", message="Đã cập nhật từ khóa Xiaohongshu.")


@router.post("/xhs/keywords/{keyword_id}/toggle")
def toggle_xhs_keyword(keyword_id: int, db: Session = Depends(get_db)):
    row = db.get(XhsKeyword, keyword_id)
    if not row:
        return _redirect("/xhs/keywords", error="Không tìm thấy từ khóa.")
    row.enabled = not row.enabled
    row.updated_at = datetime.utcnow()
    db.commit()
    return _redirect("/xhs/keywords", message="Đã đổi trạng thái từ khóa Xiaohongshu.")


@router.post("/xhs/keywords/{keyword_id}/delete")
def delete_xhs_keyword(keyword_id: int, db: Session = Depends(get_db)):
    row = db.get(XhsKeyword, keyword_id)
    if not row:
        return _redirect("/xhs/keywords", error="Không tìm thấy từ khóa.")
    db.query(XhsKeywordLink).filter(XhsKeywordLink.keyword_id == keyword_id).delete()
    db.delete(row)
    db.commit()
    return _redirect("/xhs/keywords", message="Đã xóa từ khóa Xiaohongshu.")


@router.get("/xhs/runs")
def xhs_runs_page(request: Request, db: Session = Depends(get_db)):
    runs = db.query(XhsCrawlRun).order_by(XhsCrawlRun.started_at.desc()).limit(50).all()
    return templates.TemplateResponse(
        "xhs_runs.html",
        _common(request, db, {"runs": runs}),
    )


@router.get("/xhs/posts/{post_id}")
def xhs_post_detail(request: Request, post_id: int, db: Session = Depends(get_db)):
    cards = [card for card in load_xhs_cards(db) if card.post.id == post_id]
    if not cards:
        return _redirect("/xhs", error="Không tìm thấy bài Xiaohongshu.")
    return templates.TemplateResponse(
        "xhs_post_detail.html",
        _common(request, db, {"card": cards[0]}),
    )


@router.get("/api/xhs/keywords")
def api_xhs_keywords(db: Session = Depends(get_db)):
    rows = (
        db.query(XhsKeyword)
        .filter(XhsKeyword.enabled.is_(True))
        .order_by(XhsKeyword.id)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "keyword": row.keyword,
                "vietnamese_meaning": row.vietnamese_meaning,
                "max_results": min(row.max_results or 30, 30),
            }
            for row in rows
        ]
    }


@router.get("/api/xhs/posts")
def api_xhs_posts(
    days: int | None = 7,
    keyword_id: int | None = None,
    only_relevant: int = 0,
    min_collect: int | None = None,
    min_like: int | None = None,
    sort: str = "trend_score",
    db: Session = Depends(get_db),
):
    cards = load_xhs_cards(
        db,
        days=days,
        keyword_id=keyword_id,
        only_relevant=bool(only_relevant),
        min_collect=min_collect,
        min_like=min_like,
        sort=sort,
    )
    return {"items": [xhs_card_to_dict(card) for card in cards], "count": len(cards)}


@router.get("/api/xhs/runs")
def api_xhs_runs(db: Session = Depends(get_db)):
    runs = db.query(XhsCrawlRun).order_by(XhsCrawlRun.started_at.desc()).limit(50).all()
    return {
        "items": [
            {
                "id": run.id,
                "client_run_id": run.client_run_id,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "keyword_count": run.keyword_count,
                "received_count": run.received_count,
                "accepted_count": run.accepted_count,
                "rejected_count": run.rejected_count,
                "new_post_count": run.new_post_count,
                "duplicate_count": run.duplicate_count,
                "source_filename": run.source_filename,
                "error_message": run.error_message,
            }
            for run in runs
        ]
    }


@router.post("/xhs/crawl/request")
def request_xhs_crawl(db: Session = Depends(get_db)):
    current = _get_remote_state(db)
    if current.get("status") in {"queued", "running", "waiting"}:
        return _redirect("/xhs", message="Đã có một lượt RedNote đang chờ hoặc đang chạy.")
    state = _default_remote_state()
    state.update(
        {
            "job_id": f"xhs-web-{datetime.utcnow():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}",
            "status": "queued",
            "stage": "queued",
            "message": "Đang chờ máy tính của bạn nhận lệnh",
            "requested_at": datetime.utcnow().isoformat(),
        }
    )
    _save_remote_state(db, state)
    return _redirect("/xhs", message="Đã gửi yêu cầu tìm kiếm tới máy tính của bạn.")


@router.post("/xhs/crawl/cancel")
def cancel_xhs_crawl(db: Session = Depends(get_db)):
    state = _get_remote_state(db)
    status = state.get("status")
    if status == "queued":
        state.update(
            status="cancelled",
            stage="cancelled",
            message="Đã hủy lượt tìm trước khi bắt đầu",
            finished_at=datetime.utcnow().isoformat(),
        )
    elif status in {"running", "waiting"}:
        state.update(
            status="cancelling",
            stage="cancelling",
            message="Đang dừng an toàn và lưu kết quả đã thu được",
            next_keyword_at=None,
        )
    else:
        return _redirect("/xhs", message="Không có lượt RedNote nào đang chạy.")
    _save_remote_state(db, state)
    return _redirect("/xhs", message="Đã gửi yêu cầu dừng.")


@router.post("/xhs/login/request")
def request_xhs_login(db: Session = Depends(get_db)):
    current = _get_remote_state(db)
    if current.get("status") in {"queued", "running", "waiting"}:
        return _redirect("/xhs", message="Đang có một tác vụ RedNote chạy trên máy tính.")
    state = _default_remote_state()
    state.update(
        {
            "job_id": f"xhs-login-{datetime.utcnow():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}",
            "action": "login",
            "status": "queued",
            "stage": "login_queued",
            "message": "Đang chờ máy tính mở Chrome để đăng nhập",
            "requested_at": datetime.utcnow().isoformat(),
        }
    )
    _save_remote_state(db, state)
    return _redirect("/xhs", message="Đã gửi lệnh mở Chrome tới máy tính.")


@router.get("/api/xhs/crawl/status")
def api_xhs_crawl_status(db: Session = Depends(get_db)):
    return _get_remote_state(db)


@router.post("/api/xhs/crawl/claim")
def api_xhs_crawl_claim(request: Request, db: Session = Depends(get_db)):
    auth_error = _check_ingest_token(request)
    if auth_error:
        return JSONResponse({"ok": False, "error": auth_error}, status_code=401)
    state = _get_remote_state(db)
    if state.get("status") != "queued":
        return {"ok": True, "job": None}
    state.update(
        {
            "status": "running",
            "stage": "starting",
            "message": "Máy tính đã nhận lệnh, đang mở RedNote",
            "started_at": datetime.utcnow().isoformat(),
        }
    )
    _save_remote_state(db, state)
    return {"ok": True, "job": state}


@router.post("/api/xhs/crawl/progress")
async def api_xhs_crawl_progress(request: Request, db: Session = Depends(get_db)):
    auth_error = _check_ingest_token(request)
    if auth_error:
        return JSONResponse({"ok": False, "error": auth_error}, status_code=401)
    payload = await request.json()
    state = _get_remote_state(db)
    if not payload.get("job_id") or payload.get("job_id") != state.get("job_id"):
        return JSONResponse({"ok": False, "error": "Job không còn hiệu lực."}, status_code=409)
    allowed = {
        "status", "stage", "message", "keyword", "keyword_index", "keyword_total",
        "received_count", "accepted_count", "next_keyword_at", "error", "finished_at",
    }
    for key in allowed:
        if key in payload:
            state[key] = payload[key]
    _save_remote_state(db, state)
    return {"ok": True, "state": state}


@router.get("/api/xhs/posts/{post_id}")
def api_xhs_post_detail(post_id: int, db: Session = Depends(get_db)):
    cards = [card for card in load_xhs_cards(db) if card.post.id == post_id]
    if not cards:
        return JSONResponse({"ok": False, "error": "Không tìm thấy bài."}, status_code=404)
    return {"ok": True, "item": xhs_card_to_dict(cards[0])}


@router.post("/api/xhs/ingest")
async def api_xhs_ingest(request: Request, db: Session = Depends(get_db)):
    auth_error = _check_ingest_token(request)
    if auth_error:
        return JSONResponse({"ok": False, "error": auth_error}, status_code=401)

    settings = get_settings()
    max_bytes = int(float(settings.xhs_ingest_max_body_mb) * 1024 * 1024)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                return JSONResponse(
                    {"ok": False, "error": "Payload vượt giới hạn kích thước."},
                    status_code=413,
                )
        except ValueError:
            pass
    raw = await request.body()
    if len(raw) > max_bytes:
        return JSONResponse(
            {"ok": False, "error": "Payload vượt giới hạn kích thước."},
            status_code=413,
        )
    try:
        payload = XhsIngestPayload.model_validate_json(raw)
    except Exception as exc:
        logger.warning("XHS ingest invalid payload: %s", redact_secrets(str(exc)))
        return JSONResponse(
            {"ok": False, "error": "Payload không hợp lệ."},
            status_code=422,
        )

    result = ingest_xhs_payload(db, payload)
    status = 200 if result.ok else 500
    return JSONResponse(
        {
            "ok": result.ok,
            "idempotent": result.idempotent,
            "run_id": result.run_id,
            "client_run_id": result.client_run_id,
            "received_count": result.received_count,
            "accepted_count": result.accepted_count,
            "rejected_count": result.rejected_count,
            "new_post_count": result.new_post_count,
            "duplicate_count": result.duplicate_count,
            "rejection_reasons": result.rejection_reasons,
            "error": result.error,
        },
        status_code=status,
    )
