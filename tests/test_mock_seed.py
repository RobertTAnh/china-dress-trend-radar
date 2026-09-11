from app.models import Snapshot, Video, VideoKeyword
from app.services.mock_seed import seed_mock_data
from app.services.queries import load_video_cards
from app.tikhub.mock_fixtures import MOCK_VIDEOS
from tests.conftest import make_session


def test_mock_seed_has_enough_variety():
    db = make_session()
    seed_mock_data(db)
    videos = db.query(Video).all()
    assert len(videos) >= 20
    assert len(MOCK_VIDEOS) >= 20
    missing_views = 0
    multi_keyword = 0
    for video in videos:
        snaps = db.query(Snapshot).filter(Snapshot.video_id == video.id).all()
        assert len(snaps) >= 2
        times = {item.captured_at for item in snaps}
        assert len(times) >= 2
        if any(item.view_count is None for item in snaps):
            missing_views += 1
        if db.query(VideoKeyword).filter(VideoKeyword.video_id == video.id).count() > 1:
            multi_keyword += 1
    assert missing_views >= 1
    assert multi_keyword >= 1
    top7 = load_video_cards(db, days=7, trending_only=True)
    top30 = load_video_cards(db, days=30, trending_only=True)
    assert len(top7) >= 1
    assert len(top30) >= len(top7)
    needs_review = [card for card in load_video_cards(db, days=30, include_needs_review=True) if card.trend and card.trend.needs_review]
    assert needs_review
    db.close()
