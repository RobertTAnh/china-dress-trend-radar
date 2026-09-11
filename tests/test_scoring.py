from datetime import datetime, timedelta
from math import log

from app.models import Snapshot, Video
from app.services.scoring import recency_multiplier, score_snapshots
from tests.conftest import make_session


def _video_with_snaps(db, published_days: int, views=(100, 400), likes=(10, 40), drop=False):
    published = datetime.utcnow() - timedelta(days=published_days)
    video = Video(
        platform="douyin",
        external_video_id=f"score-{published_days}-{views[0]}",
        source_url="https://www.douyin.com/video/x",
        caption="法式收腰连衣裙女试穿",
        author_name="A",
        published_at=published,
        first_seen_at=published,
        last_seen_at=datetime.utcnow(),
    )
    db.add(video)
    db.flush()
    t0 = datetime.utcnow() - timedelta(hours=24)
    t1 = datetime.utcnow()
    second_views, second_likes = views[1], likes[1]
    if drop:
        second_views, second_likes = 10, 1
    db.add(Snapshot(video_id=video.id, captured_at=t0, view_count=views[0], like_count=likes[0], comment_count=2, share_count=2, collect_count=2))
    db.add(Snapshot(video_id=video.id, captured_at=t1, view_count=second_views, like_count=second_likes, comment_count=1 if drop else 8, share_count=1 if drop else 6, collect_count=1 if drop else 7))
    db.commit()
    db.refresh(video)
    return video


def test_delta_and_velocity():
    db = make_session()
    video = _video_with_snaps(db, 2, views=(100, 400), likes=(10, 40))
    result = score_snapshots(video, list(video.snapshots))
    assert result is not None
    assert result.delta_views == 300
    assert result.delta_likes == 30
    assert result.hours_between > 0
    assert abs(result.view_velocity - (300 / result.hours_between)) < 1e-6
    db.close()


def test_trend_score_formula_and_recency():
    db = make_session()
    video = _video_with_snaps(db, 2, views=(100, 400), likes=(10, 40))
    result = score_snapshots(video, list(video.snapshots))
    latest = max(video.snapshots, key=lambda s: s.captured_at)
    previous = min(video.snapshots, key=lambda s: s.captured_at)
    expected = (
        log(1 + 300) * 1
        + log(1 + 30) * 3
        + log(1 + 6) * 4
        + log(1 + 4) * 5
        + log(1 + 5) * 4
    ) * recency_multiplier(video.published_at, latest.captured_at)
    assert abs(result.trend_score - round(expected, 4)) < 1e-6
    assert result.recency_multiplier == 1.5
    assert previous.view_count == 100
    db.close()


def test_score_without_views():
    db = make_session()
    published = datetime.utcnow() - timedelta(days=5)
    video = Video(
        platform="douyin",
        external_video_id="no-views",
        source_url="https://www.douyin.com/video/nv",
        caption="吊带网纱长裙女试穿",
        published_at=published,
        first_seen_at=published,
        last_seen_at=datetime.utcnow(),
    )
    db.add(video)
    db.flush()
    t0 = datetime.utcnow() - timedelta(hours=12)
    t1 = datetime.utcnow()
    db.add(Snapshot(video_id=video.id, captured_at=t0, view_count=None, like_count=10, comment_count=2, share_count=2, collect_count=2))
    db.add(Snapshot(video_id=video.id, captured_at=t1, view_count=None, like_count=40, comment_count=8, share_count=6, collect_count=7))
    db.commit()
    db.refresh(video)
    result = score_snapshots(video, list(video.snapshots))
    assert result.delta_views is None
    assert result.delta_likes == 30
    assert result.trend_score > 0
    assert result.recency_multiplier == 1.25
    db.close()


def test_anomalous_drop_needs_review():
    db = make_session()
    video = _video_with_snaps(db, 1, drop=True)
    result = score_snapshots(video, list(video.snapshots))
    assert result.needs_review is True
    db.close()


def test_requires_two_snapshots():
    db = make_session()
    video = Video(
        platform="douyin",
        external_video_id="one-snap",
        source_url="https://www.douyin.com/video/o",
        caption="气质小黑裙女试穿",
        published_at=datetime.utcnow(),
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(video)
    db.flush()
    db.add(Snapshot(video_id=video.id, captured_at=datetime.utcnow(), like_count=1))
    db.commit()
    db.refresh(video)
    assert score_snapshots(video, list(video.snapshots)) is None
    db.close()
