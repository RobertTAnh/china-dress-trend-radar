from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, selectinload

from app.models import Keyword, Snapshot, Video, VideoKeyword
from app.services.scoring import TrendResult, score_snapshots
from app.services.relevance import is_relevant_video


@dataclass
class VideoCard:
    video: Video
    trend: TrendResult | None
    keywords: list[str]
    latest: Snapshot | None


def _window_start(days: int | None) -> datetime | None:
    if not days:
        return None
    return datetime.utcnow() - timedelta(days=days)


def load_video_cards(
    db: Session,
    days: int | None = 7,
    keyword_id: int | None = None,
    min_score: float | None = None,
    only_new: bool = False,
    include_needs_review: bool = False,
    sort: str = "trend_score",
    limit: int | None = None,
    trending_only: bool = False,
) -> list[VideoCard]:
    query = db.query(Video).options(
        selectinload(Video.snapshots),
        selectinload(Video.keywords).selectinload(VideoKeyword.keyword),
    )
    start = _window_start(days)
    if start is not None:
        query = query.filter(
            (Video.published_at >= start) | ((Video.published_at.is_(None)) & (Video.first_seen_at >= start))
        )
    if only_new and start is not None:
        query = query.filter(Video.first_seen_at >= start)
    if keyword_id:
        query = query.join(VideoKeyword).filter(VideoKeyword.keyword_id == keyword_id)

    cards: list[VideoCard] = []
    for video in query.all():
        if not is_relevant_video(
            video.caption,
            video.hashtags_json,
            author_name=video.author_name,
        ):
            continue
        trend = score_snapshots(video, list(video.snapshots))
        if trending_only:
            if trend is None:
                continue
            if trend.needs_review and not include_needs_review:
                continue
        if min_score is not None:
            if trend is None or trend.trend_score < min_score:
                continue
        latest = None
        if video.snapshots:
            latest = max(video.snapshots, key=lambda item: item.captured_at)
        names = [link.keyword.keyword for link in video.keywords if link.keyword]
        cards.append(VideoCard(video=video, trend=trend, keywords=names, latest=latest))

    def sort_key(card: VideoCard):
        if sort == "like_velocity":
            return card.trend.like_velocity if card.trend and card.trend.like_velocity is not None else -1
        if sort == "published_at":
            return card.video.published_at or datetime.min
        if sort == "first_seen_at":
            return card.video.first_seen_at
        return card.trend.trend_score if card.trend else -1

    cards.sort(key=sort_key, reverse=True)
    if limit:
        return cards[:limit]
    return cards
