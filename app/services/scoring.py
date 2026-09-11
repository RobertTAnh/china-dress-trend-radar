from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import log

from app.models import Snapshot, Video


@dataclass
class TrendResult:
    video_id: int
    age_hours: float
    hours_between: float
    delta_views: int | None
    delta_likes: int | None
    delta_comments: int | None
    delta_shares: int | None
    delta_collects: int | None
    view_velocity: float | None
    like_velocity: float | None
    trend_score: float
    recency_multiplier: float
    needs_review: bool
    latest: Snapshot
    previous: Snapshot


def _delta(new: int | None, old: int | None) -> int | None:
    if new is None or old is None:
        return None
    return new - old


def _velocity(delta: int | None, hours: float) -> float | None:
    if delta is None or hours <= 0:
        return None
    return delta / hours


def recency_multiplier(published_at: datetime | None, latest_at: datetime) -> float:
    if published_at is None:
        return 1.0
    age = latest_at - published_at
    if age <= timedelta(days=3):
        return 1.5
    if age <= timedelta(days=7):
        return 1.25
    if age <= timedelta(days=30):
        return 1.0
    return 0.5


def _log_term(delta: int | None, weight: float) -> float:
    if delta is None:
        return 0.0
    return log(1 + max(delta, 0)) * weight


def is_anomalous_drop(latest: Snapshot, previous: Snapshot) -> bool:
    pairs = [
        (latest.like_count, previous.like_count),
        (latest.comment_count, previous.comment_count),
        (latest.share_count, previous.share_count),
        (latest.collect_count, previous.collect_count),
        (latest.view_count, previous.view_count),
    ]
    available = [(new, old) for new, old in pairs if new is not None and old is not None]
    if not available:
        return False
    for new, old in available:
        if old > 0 and new < old * 0.5:
            return True
    core = [
        (latest.like_count, previous.like_count),
        (latest.comment_count, previous.comment_count),
        (latest.share_count, previous.share_count),
        (latest.collect_count, previous.collect_count),
    ]
    core_available = [(new, old) for new, old in core if new is not None and old is not None]
    if len(core_available) >= 2 and all(new < old for new, old in core_available):
        return True
    return False


def score_snapshots(
    video: Video,
    snapshots: list[Snapshot],
) -> TrendResult | None:
    ordered = sorted(snapshots, key=lambda item: item.captured_at)
    unique_times = []
    for snap in ordered:
        if not unique_times or unique_times[-1].captured_at != snap.captured_at:
            unique_times.append(snap)
    if len(unique_times) < 2:
        return None
    previous, latest = unique_times[-2], unique_times[-1]
    hours = (latest.captured_at - previous.captured_at).total_seconds() / 3600
    if hours <= 0:
        hours = 1 / 60
    published = video.published_at
    latest_at = latest.captured_at
    age_hours = 0.0
    if published:
        age_hours = max((latest_at - published).total_seconds() / 3600, 0)
    delta_views = _delta(latest.view_count, previous.view_count)
    delta_likes = _delta(latest.like_count, previous.like_count)
    delta_comments = _delta(latest.comment_count, previous.comment_count)
    delta_shares = _delta(latest.share_count, previous.share_count)
    delta_collects = _delta(latest.collect_count, previous.collect_count)
    base = (
        _log_term(delta_views, 1)
        + _log_term(delta_likes, 3)
        + _log_term(delta_comments, 4)
        + _log_term(delta_shares, 5)
        + _log_term(delta_collects, 4)
    )
    multiplier = recency_multiplier(published, latest_at)
    return TrendResult(
        video_id=video.id,
        age_hours=age_hours,
        hours_between=hours,
        delta_views=delta_views,
        delta_likes=delta_likes,
        delta_comments=delta_comments,
        delta_shares=delta_shares,
        delta_collects=delta_collects,
        view_velocity=_velocity(delta_views, hours),
        like_velocity=_velocity(delta_likes, hours),
        trend_score=round(base * multiplier, 4),
        recency_multiplier=multiplier,
        needs_review=is_anomalous_drop(latest, previous),
        latest=latest,
        previous=previous,
    )


def format_delta(value: int | None) -> str:
    if value is None:
        return "—"
    if value > 0:
        return f"+{value:,}".replace(",", ".")
    return f"{value:,}".replace(",", ".")
