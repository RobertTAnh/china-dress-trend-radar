from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Keyword, Snapshot, Video, VideoKeyword
from app.tikhub.mock_fixtures import CROSS_KEYWORD_LINKS, MOCK_VIDEOS
from app.tikhub.normalizer import normalize_video
from app.services.seed_defaults import seed_defaults

logger = logging.getLogger(__name__)


def _snapshot_at(base: datetime, hours_ago: int, metrics: dict, drop: bool = False) -> dict:
    captured = base - timedelta(hours=hours_ago)
    values = dict(metrics)
    if drop:
        for key in ("like_count", "comment_count", "share_count", "collect_count", "view_count"):
            if values.get(key):
                values[key] = max(int(values[key] * 0.3), 0)
    return {"captured_at": captured, **values}


def seed_mock_data(db: Session, reset_videos: bool = False) -> int:
    seed_defaults(db)
    if reset_videos:
        db.query(Snapshot).delete()
        db.query(VideoKeyword).delete()
        db.query(Video).delete()
        db.commit()

    keywords = {item.keyword: item for item in db.query(Keyword).all()}
    created = 0
    now = datetime.utcnow()

    for index, item in enumerate(MOCK_VIDEOS):
        aweme = item["data"]["aweme_info"]
        video = normalize_video(aweme)
        if video is None:
            continue
        existing = (
            db.query(Video)
            .filter(Video.external_video_id == video.external_video_id)
            .one_or_none()
        )
        if existing:
            db_video = existing
        else:
            db_video = Video(
                platform="douyin",
                external_video_id=video.external_video_id,
                source_url=video.source_url,
                caption=video.caption,
                author_id=video.author_id,
                author_name=video.author_name,
                published_at=video.published_at,
                cover_url=video.cover_url,
                duration=video.duration,
                hashtags_json=video.hashtags,
                first_seen_at=now - timedelta(days=4),
                last_seen_at=now,
                raw_data_json=video.raw_data,
            )
            db.add(db_video)
            db.flush()
            created += 1

        keyword_names = CROSS_KEYWORD_LINKS.get(
            video.external_video_id,
            [aweme["cha_list"][0]["cha_name"].lstrip("#")],
        )
        for name in keyword_names:
            keyword = keywords.get(name)
            if not keyword:
                continue
            link = (
                db.query(VideoKeyword)
                .filter(
                    VideoKeyword.video_id == db_video.id,
                    VideoKeyword.keyword_id == keyword.id,
                )
                .one_or_none()
            )
            if link is None:
                db.add(
                    VideoKeyword(
                        video_id=db_video.id,
                        keyword_id=keyword.id,
                        first_seen_at=now - timedelta(days=3),
                    )
                )

        metrics = {
            "view_count": video.metrics.view_count,
            "like_count": video.metrics.like_count or 0,
            "comment_count": video.metrics.comment_count or 0,
            "share_count": video.metrics.share_count or 0,
            "collect_count": video.metrics.collect_count or 0,
        }
        older = {
            "view_count": None if metrics["view_count"] is None else max(metrics["view_count"] // 3, 0),
            "like_count": max((metrics["like_count"] or 0) // 3, 0),
            "comment_count": max((metrics["comment_count"] or 0) // 3, 0),
            "share_count": max((metrics["share_count"] or 0) // 3, 0),
            "collect_count": max((metrics["collect_count"] or 0) // 3, 0),
        }
        mid = {
            "view_count": None if metrics["view_count"] is None else max(int(metrics["view_count"] * 0.7), 0),
            "like_count": max(int((metrics["like_count"] or 0) * 0.7), 0),
            "comment_count": max(int((metrics["comment_count"] or 0) * 0.7), 0),
            "share_count": max(int((metrics["share_count"] or 0) * 0.7), 0),
            "collect_count": max(int((metrics["collect_count"] or 0) * 0.7), 0),
        }

        points = [
            _snapshot_at(now, 72, older),
            _snapshot_at(now, 24, mid),
            _snapshot_at(now, 0, metrics, drop=(index == 3)),
        ]
        if index % 3 == 0:
            points = [points[0], points[2]]
        for point in points:
            exists = (
                db.query(Snapshot)
                .filter(
                    Snapshot.video_id == db_video.id,
                    Snapshot.captured_at == point["captured_at"],
                )
                .one_or_none()
            )
            if exists:
                continue
            db.add(
                Snapshot(
                    video_id=db_video.id,
                    captured_at=point["captured_at"],
                    view_count=point["view_count"],
                    like_count=point["like_count"],
                    comment_count=point["comment_count"],
                    share_count=point["share_count"],
                    collect_count=point["collect_count"],
                )
            )
    db.commit()
    logger.info("Seeded mock data, new videos=%s", created)
    return created
