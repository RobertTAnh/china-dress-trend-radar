from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.constants import XHS_TREND_WEIGHTS


@dataclass
class XhsRankResult:
    score: float
    label: str
    components: dict[str, float]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _log_count_score(count: int | None, scale: float = 5.0) -> float:
    if count is None or count <= 0:
        return 0.0
    return _clamp((math.log10(count + 1) / scale) * 100.0)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def _freshness_score(published_at: datetime | None, now: datetime | None = None) -> float:
    current = _naive_utc(now) or datetime.utcnow()
    published = _naive_utc(published_at)
    if published is None:
        return 40.0
    age = current - published
    if age <= timedelta(days=7):
        return 100.0
    if age <= timedelta(days=30):
        return 70.0
    if age <= timedelta(days=90):
        return 35.0
    return 10.0


def load_weights(overrides: dict[str, float] | None = None) -> dict[str, float]:
    weights = dict(XHS_TREND_WEIGHTS)
    if overrides:
        weights.update(overrides)
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def rank_xhs_post(
    *,
    relevance_score: float,
    like_count: int | None,
    collect_count: int | None,
    comment_count: int | None,
    published_at: datetime | None = None,
    previous_collect_count: int | None = None,
    now: datetime | None = None,
    weights: dict[str, float] | None = None,
) -> XhsRankResult:
    resolved = load_weights(weights)
    rel = _clamp(float(relevance_score))
    collect = _log_count_score(collect_count)
    if previous_collect_count is not None and collect_count is not None:
        growth = max(collect_count - previous_collect_count, 0)
        collect = _clamp(0.7 * collect + 0.3 * _log_count_score(growth, scale=4.0))
    like = _log_count_score(like_count)
    comment = _log_count_score(comment_count, scale=4.0)
    freshness = _freshness_score(published_at, now=now)

    components = {
        "relevance": rel,
        "collect": collect,
        "like": like,
        "comment": comment,
        "freshness": freshness,
    }
    score = round(
        _clamp(
            resolved["relevance"] * rel
            + resolved["collect"] * collect
            + resolved["like"] * like
            + resolved["comment"] * comment
            + resolved["freshness"] * freshness
        ),
        2,
    )

    if rel < 50:
        label = "không phù hợp"
    elif rel < 70:
        label = "cần xem lại"
    else:
        label = "phù hợp"

    return XhsRankResult(score=score, label=label, components=components)
