from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models import XhsKeywordLink, XhsPost, XhsPostSnapshot
from app.services.xhs_ranking import rank_xhs_post
from app.services.xhs_relevance import xhs_relevance


@dataclass
class XhsPostCard:
    post: XhsPost
    snapshot: XhsPostSnapshot | None
    relevance_score: float
    trend_score: float
    trend_label: str
    keywords: list[str]
    is_relevant: bool


def _latest_snapshot(post: XhsPost) -> XhsPostSnapshot | None:
    if not post.snapshots:
        return None
    return max(post.snapshots, key=lambda s: (s.captured_at, s.id))


def load_xhs_cards(
    db: Session,
    *,
    days: int | None = None,
    keyword_id: int | None = None,
    only_relevant: bool = False,
    min_collect: int | None = None,
    min_like: int | None = None,
    sort: str = "trend_score",
    limit: int | None = None,
) -> list[XhsPostCard]:
    query = db.query(XhsPost).options(
        joinedload(XhsPost.snapshots),
        joinedload(XhsPost.keywords).joinedload(XhsKeywordLink.keyword),
    )
    if keyword_id is not None:
        query = query.join(XhsKeywordLink).filter(XhsKeywordLink.keyword_id == keyword_id)
    if days in (7, 30):
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = query.filter(
            (XhsPost.published_at >= cutoff) | (XhsPost.published_at.is_(None) & (XhsPost.first_seen_at >= cutoff))
        )
    posts = query.order_by(XhsPost.last_seen_at.desc()).all()

    cards: list[XhsPostCard] = []
    for post in posts:
        snapshot = _latest_snapshot(post)
        relevance = xhs_relevance(post.title, post.description, post.author_name)
        rel_score = (
            snapshot.relevance_score if snapshot and snapshot.relevance_score is not None else relevance.score
        )
        trend_score = snapshot.trend_score if snapshot and snapshot.trend_score is not None else 0.0
        trend_label = snapshot.trend_label if snapshot and snapshot.trend_label else (
            "phù hợp" if relevance.accepted and rel_score >= 70 else (
                "cần xem lại" if relevance.accepted else "không phù hợp"
            )
        )
        if snapshot is None:
            rank = rank_xhs_post(
                relevance_score=relevance.score,
                like_count=None,
                collect_count=None,
                comment_count=None,
                published_at=post.published_at,
            )
            trend_score = rank.score
            trend_label = rank.label

        if only_relevant and not relevance.accepted:
            continue
        collect = snapshot.collect_count if snapshot else None
        likes = snapshot.like_count if snapshot else None
        if min_collect is not None and (collect is None or collect < min_collect):
            continue
        if min_like is not None and (likes is None or likes < min_like):
            continue

        keywords = [
            link.keyword.keyword
            for link in post.keywords
            if link.keyword is not None
        ]
        cards.append(
            XhsPostCard(
                post=post,
                snapshot=snapshot,
                relevance_score=float(rel_score or 0),
                trend_score=float(trend_score or 0),
                trend_label=trend_label,
                keywords=keywords,
                is_relevant=relevance.accepted,
            )
        )

    if sort == "collect":
        cards.sort(
            key=lambda c: (c.snapshot.collect_count if c.snapshot and c.snapshot.collect_count else -1),
            reverse=True,
        )
    elif sort == "published_at":
        cards.sort(key=lambda c: c.post.published_at or c.post.first_seen_at, reverse=True)
    else:
        cards.sort(key=lambda c: c.trend_score, reverse=True)

    if limit is not None:
        return cards[:limit]
    return cards


def xhs_card_to_dict(card: XhsPostCard) -> dict:
    post = card.post
    snap = card.snapshot
    return {
        "id": post.id,
        "external_post_id": post.external_post_id,
        "title": post.title,
        "description": post.description,
        "author_name": post.author_name,
        "source_url": post.source_url,
        "cover_url": post.cover_url,
        "media_type": post.media_type,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "first_seen_at": post.first_seen_at.isoformat() if post.first_seen_at else None,
        "like_count": snap.like_count if snap else None,
        "collect_count": snap.collect_count if snap else None,
        "comment_count": snap.comment_count if snap else None,
        "share_count": snap.share_count if snap else None,
        "relevance_score": card.relevance_score,
        "trend_score": card.trend_score,
        "trend_label": card.trend_label,
        "keywords": card.keywords,
        "is_relevant": card.is_relevant,
    }
