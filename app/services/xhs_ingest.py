from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import XhsCrawlRun, XhsKeyword, XhsKeywordLink, XhsPost, XhsPostSnapshot
from app.services.seed_defaults import get_setting_float
from app.services.xhs_ranking import rank_xhs_post
from app.services.xhs_relevance import xhs_relevance
from app.xhs.normalizer import NormalizedXhsPost, normalize_xhs_item
from app.xhs.schemas import XhsIngestPayload

logger = logging.getLogger(__name__)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


@dataclass
class XhsIngestResult:
    ok: bool
    idempotent: bool
    run_id: int | None
    client_run_id: str
    received_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    new_post_count: int = 0
    duplicate_count: int = 0
    rejection_reasons: list[dict] = field(default_factory=list)
    error: str | None = None


def _trend_weights(db: Session) -> dict[str, float]:
    return {
        "relevance": get_setting_float(db, "xhs_trend_weight_relevance", 0.35),
        "collect": get_setting_float(db, "xhs_trend_weight_collect", 0.30),
        "like": get_setting_float(db, "xhs_trend_weight_like", 0.20),
        "comment": get_setting_float(db, "xhs_trend_weight_comment", 0.05),
        "freshness": get_setting_float(db, "xhs_trend_weight_freshness", 0.10),
    }


def _run_to_result(run: XhsCrawlRun, *, idempotent: bool) -> XhsIngestResult:
    return XhsIngestResult(
        ok=run.status == "success",
        idempotent=idempotent,
        run_id=run.id,
        client_run_id=run.client_run_id,
        received_count=run.received_count,
        accepted_count=run.accepted_count,
        rejected_count=run.rejected_count,
        new_post_count=run.new_post_count,
        duplicate_count=run.duplicate_count,
        error=run.error_message,
    )


def _upsert_post(
    db: Session,
    item: NormalizedXhsPost,
    keyword: XhsKeyword | None,
    captured_at: datetime,
    run: XhsCrawlRun,
    relevance_score: int,
    trend_score: float,
    trend_label: str,
    previous_collect: int | None,
) -> tuple[XhsPost, bool]:
    existing = (
        db.query(XhsPost)
        .filter(XhsPost.external_post_id == item.external_post_id)
        .one_or_none()
    )
    created = False
    if existing is None:
        existing = XhsPost(
            external_post_id=item.external_post_id,
            title=item.title or "",
            description=item.description or "",
            author_id=item.author_id or "",
            author_name=item.author_name or "",
            source_url=item.source_url or "",
            cover_url=item.cover_url or "",
            media_type=item.media_type or "note",
            published_at=item.published_at,
            first_seen_at=captured_at,
            last_seen_at=captured_at,
            raw_json=item.raw_json,
        )
        db.add(existing)
        db.flush()
        created = True
    else:
        existing.title = item.title or existing.title
        existing.description = item.description or existing.description
        existing.author_id = item.author_id or existing.author_id
        existing.author_name = item.author_name or existing.author_name
        existing.source_url = item.source_url or existing.source_url
        existing.cover_url = item.cover_url or existing.cover_url
        existing.media_type = item.media_type or existing.media_type
        existing.published_at = item.published_at or existing.published_at
        existing.last_seen_at = captured_at
        existing.raw_json = item.raw_json or existing.raw_json

    if keyword is not None:
        link = (
            db.query(XhsKeywordLink)
            .filter(
                XhsKeywordLink.post_id == existing.id,
                XhsKeywordLink.keyword_id == keyword.id,
            )
            .one_or_none()
        )
        if link is None:
            db.add(
                XhsKeywordLink(
                    post_id=existing.id,
                    keyword_id=keyword.id,
                    first_seen_at=captured_at,
                    last_seen_at=captured_at,
                    best_search_position=item.search_position,
                )
            )
        else:
            link.last_seen_at = captured_at
            if item.search_position is not None:
                if (
                    link.best_search_position is None
                    or item.search_position < link.best_search_position
                ):
                    link.best_search_position = item.search_position

    snapshot = (
        db.query(XhsPostSnapshot)
        .filter(
            XhsPostSnapshot.post_id == existing.id,
            XhsPostSnapshot.crawl_run_id == run.id,
        )
        .one_or_none()
    )
    if snapshot is None:
        snapshot = XhsPostSnapshot(
            post_id=existing.id,
            crawl_run_id=run.id,
            captured_at=captured_at,
        )
        db.add(snapshot)
    snapshot.captured_at = captured_at
    snapshot.like_count = item.like_count
    snapshot.collect_count = item.collect_count
    snapshot.comment_count = item.comment_count
    snapshot.share_count = item.share_count
    snapshot.relevance_score = float(relevance_score)
    snapshot.trend_score = trend_score
    snapshot.trend_label = trend_label
    _ = previous_collect
    db.flush()
    return existing, created


def ingest_xhs_payload(db: Session, payload: XhsIngestPayload) -> XhsIngestResult:
    settings = get_settings()
    max_per_keyword = max(1, min(int(settings.xhs_max_items_per_keyword), 30))
    existing = (
        db.query(XhsCrawlRun)
        .filter(XhsCrawlRun.client_run_id == payload.client_run_id)
        .one_or_none()
    )
    if existing is not None and existing.status == "success":
        logger.info(
            "XHS ingest idempotent client_run_id=%s run_id=%s accepted=%s",
            payload.client_run_id,
            existing.id,
            existing.accepted_count,
        )
        result = _run_to_result(existing, idempotent=True)
        result.rejection_reasons = [{"reason": "Đã ingest client_run_id này trước đó."}]
        return result

    run = existing
    if run is None:
        run = XhsCrawlRun(
            client_run_id=payload.client_run_id,
            status="running",
            started_at=_naive_utc(payload.started_at) or datetime.utcnow(),
            source_filename=(payload.source_filename or "")[:255],
            keyword_count=len(payload.keywords),
        )
        db.add(run)
        db.flush()
    else:
        run.status = "running"
        run.error_message = None
        run.started_at = _naive_utc(payload.started_at) or run.started_at
        run.source_filename = (payload.source_filename or run.source_filename or "")[:255]
        run.keyword_count = len(payload.keywords)

    captured_at = _naive_utc(payload.finished_at) or datetime.utcnow()
    weights = _trend_weights(db)
    seen_ids: set[str] = set()
    received = 0
    accepted = 0
    rejected = 0
    new_count = 0
    duplicates = 0
    reasons: list[dict] = []

    try:
        for batch in payload.keywords:
            keyword_row = (
                db.query(XhsKeyword)
                .filter(XhsKeyword.keyword == batch.keyword)
                .one_or_none()
            )
            items = list(batch.items or [])
            if len(items) > max_per_keyword:
                extra = len(items) - max_per_keyword
                reasons.append(
                    {
                        "keyword": batch.keyword,
                        "reason": f"Cắt còn {max_per_keyword} bài/từ khóa (bỏ {extra}).",
                    }
                )
                items = items[:max_per_keyword]

            for index, raw in enumerate(items, start=1):
                received += 1
                if not isinstance(raw, dict):
                    rejected += 1
                    reasons.append(
                        {
                            "keyword": batch.keyword,
                            "reason": "Item không phải object JSON",
                            "position": index,
                        }
                    )
                    continue
                normalized, error = normalize_xhs_item(
                    raw, keyword=batch.keyword, search_position=index
                )
                if normalized is None or error:
                    rejected += 1
                    reasons.append(
                        {
                            "keyword": batch.keyword,
                            "reason": error or "Không chuẩn hóa được",
                            "position": index,
                        }
                    )
                    continue
                if normalized.external_post_id in seen_ids:
                    duplicates += 1
                    continue
                seen_ids.add(normalized.external_post_id)

                relevance = xhs_relevance(
                    normalized.title,
                    normalized.description,
                    normalized.author_name,
                )
                if not relevance.accepted:
                    rejected += 1
                    reasons.append(
                        {
                            "keyword": batch.keyword,
                            "external_post_id": normalized.external_post_id,
                            "title": (normalized.title or "")[:80],
                            "reason": "; ".join(relevance.rejection_reasons or relevance.reasons),
                            "matched_negative_terms": relevance.matched_negative_terms,
                        }
                    )
                    logger.info(
                        "XHS reject id=%s title=%s reasons=%s",
                        normalized.external_post_id,
                        (normalized.title or "")[:80],
                        "; ".join(relevance.rejection_reasons or relevance.reasons),
                    )
                    continue

                previous = (
                    db.query(XhsPost)
                    .filter(XhsPost.external_post_id == normalized.external_post_id)
                    .one_or_none()
                )
                prev_collect = None
                if previous is not None and previous.snapshots:
                    latest = max(previous.snapshots, key=lambda s: (s.captured_at, s.id))
                    prev_collect = latest.collect_count

                rank = rank_xhs_post(
                    relevance_score=relevance.score,
                    like_count=normalized.like_count,
                    collect_count=normalized.collect_count,
                    comment_count=normalized.comment_count,
                    published_at=normalized.published_at,
                    previous_collect_count=prev_collect,
                    now=captured_at,
                    weights=weights,
                )
                _post, created = _upsert_post(
                    db,
                    normalized,
                    keyword_row,
                    captured_at,
                    run,
                    relevance.score,
                    rank.score,
                    rank.label,
                    prev_collect,
                )
                accepted += 1
                if created:
                    new_count += 1
                else:
                    duplicates += 1

        run.received_count = received
        run.accepted_count = accepted
        run.rejected_count = rejected
        run.new_post_count = new_count
        run.duplicate_count = duplicates
        run.status = "success"
        run.finished_at = datetime.utcnow()
        db.commit()
        logger.info(
            "XHS ingest done client_run_id=%s received=%s accepted=%s rejected=%s new=%s dup=%s",
            payload.client_run_id,
            received,
            accepted,
            rejected,
            new_count,
            duplicates,
        )
        result = _run_to_result(run, idempotent=False)
        result.rejection_reasons = reasons
        return result
    except Exception as exc:
        db.rollback()
        if run.id is None:
            db.add(run)
        run.status = "error"
        run.error_message = "Lỗi ingest Xiaohongshu."
        run.finished_at = datetime.utcnow()
        run.received_count = received
        run.accepted_count = accepted
        run.rejected_count = rejected
        run.new_post_count = new_count
        run.duplicate_count = duplicates
        db.commit()
        logger.exception("XHS ingest failed client_run_id=%s", payload.client_run_id)
        return XhsIngestResult(
            ok=False,
            idempotent=False,
            run_id=run.id,
            client_run_id=payload.client_run_id,
            received_count=received,
            accepted_count=accepted,
            rejected_count=rejected,
            new_post_count=new_count,
            duplicate_count=duplicates,
            rejection_reasons=reasons,
            error=str(exc),
        )
