from datetime import datetime

from app.models import Keyword, Snapshot, Video, VideoKeyword
from app.services.crawler import upsert_video
from tests.conftest import make_session, normalized


def test_dedup_by_external_video_id():
    db = make_session()
    keywords = db.query(Keyword).all()
    kw1, kw2 = keywords[0], keywords[1]
    captured = datetime(2026, 9, 11, 10, 0, 0)
    item = normalized("ext-1", url="https://www.douyin.com/video/ext-1")
    video1, created1 = upsert_video(db, item, kw1, captured)
    db.commit()
    item.source_url = "https://www.douyin.com/video/ext-1-new"
    video2, created2 = upsert_video(db, item, kw2, captured)
    db.commit()
    videos = db.query(Video).filter(Video.external_video_id == "ext-1").all()
    assert created1 is True
    assert created2 is False
    assert video1.id == video2.id
    assert len(videos) == 1
    assert videos[0].source_url.endswith("ext-1-new")
    links = db.query(VideoKeyword).filter(VideoKeyword.video_id == videos[0].id).all()
    assert {link.keyword_id for link in links} == {kw1.id, kw2.id}
    snaps = db.query(Snapshot).filter(Snapshot.video_id == videos[0].id).all()
    assert len(snaps) == 1
    db.close()
