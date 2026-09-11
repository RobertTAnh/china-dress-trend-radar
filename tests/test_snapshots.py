from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.models import Snapshot, Video
from app.services.crawler import upsert_video
from tests.conftest import make_session, normalized


def test_snapshot_saved_and_unique_per_run():
    db = make_session()
    captured = datetime(2026, 9, 1, 8, 0, 0)
    item = normalized("snap-1", views=100, likes=10)
    video, _ = upsert_video(db, item, None, captured)
    db.commit()
    upsert_video(db, item, None, captured)
    db.commit()
    snaps = db.query(Snapshot).filter(Snapshot.video_id == video.id).all()
    assert len(snaps) == 1
    assert snaps[0].view_count == 100

    later = captured + timedelta(days=2)
    item.metrics.view_count = 250
    item.metrics.like_count = 40
    upsert_video(db, item, None, later)
    db.commit()
    snaps = db.query(Snapshot).filter(Snapshot.video_id == video.id).order_by(Snapshot.captured_at).all()
    assert len(snaps) == 2
    assert snaps[0].view_count == 100
    assert snaps[1].view_count == 250

    duplicate = Snapshot(video_id=video.id, captured_at=later, like_count=1)
    db.add(duplicate)
    try:
        db.commit()
        assert False, "expected unique constraint"
    except IntegrityError:
        db.rollback()
    db.close()
