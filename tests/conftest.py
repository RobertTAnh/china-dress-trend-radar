from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 — register product tables on Base.metadata
from app.database import Base
from app.models import Keyword, Snapshot, Video
from app.services.seed_defaults import seed_defaults
from app.tikhub.normalizer import NormalizedMetrics, NormalizedVideo


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    seed_defaults(db)
    return db


def sample_aweme(
    aweme_id: str = "123",
    desc: str = "法式收腰连衣裙女试穿 #连衣裙",
    likes: int = 100,
    views: int | None = 1000,
    create_time: int | None = 1710000000,
) -> dict:
    stats = {"digg_count": likes, "comment_count": 10, "share_count": 5, "collect_count": 8}
    if views is not None:
        stats["play_count"] = views
    return {
        "aweme_id": aweme_id,
        "desc": desc,
        "create_time": create_time,
        "share_url": f"https://www.douyin.com/video/{aweme_id}",
        "author": {"uid": "u1", "nickname": "Shop A"},
        "video": {"duration": 12000, "cover": {"url_list": ["https://example.com/cover.jpg"]}},
        "cha_list": [{"cha_name": "#连衣裙"}],
        "statistics": stats,
    }


def sample_search_payload(videos: list[dict], cursor: int = 8, has_more: int = 1, search_id: str = "sid", backtrace: str = "bt") -> dict:
    return {
        "code": 200,
        "data": {
            "business_data": [{"type": 1, "data": {"aweme_info": item}} for item in videos],
            "cursor": cursor,
            "has_more": has_more,
            "search_id": search_id,
            "backtrace": backtrace,
        },
    }


def normalized(
    video_id: str,
    views: int | None = 10,
    likes: int = 5,
    caption: str = "法式收腰连衣裙女试穿",
    url: str = "",
) -> NormalizedVideo:
    return NormalizedVideo(
        external_video_id=video_id,
        source_url=url or f"https://www.douyin.com/video/{video_id}",
        caption=caption,
        author_id="u1",
        author_name="Author",
        published_at=datetime.utcnow() - timedelta(days=2),
        cover_url="https://example.com/a.jpg",
        duration=12,
        hashtags=["连衣裙"],
        metrics=NormalizedMetrics(
            view_count=views,
            like_count=likes,
            comment_count=1,
            share_count=1,
            collect_count=1,
        ),
        raw_data={"aweme_id": video_id},
    )
