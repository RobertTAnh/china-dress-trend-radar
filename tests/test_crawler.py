import pytest

from app.models import AppSetting, Snapshot, Video, VideoKeyword
from app.services.crawler import run_crawl
from app.tikhub.adapter import TikHubAdapter
from tests.conftest import make_session


@pytest.mark.asyncio
async def test_mock_crawl_dedup_and_snapshots():
    db = make_session()
    adapter = TikHubAdapter(mock_mode=True)
    run = await run_crawl(db, adapter=adapter)
    assert run.status in {"success", "budget_stopped"}
    assert run.request_count > 0
    video_count = db.query(Video).count()
    assert video_count >= 10
    links = db.query(VideoKeyword).count()
    assert links >= video_count
    snap_count = db.query(Snapshot).count()
    assert snap_count >= video_count
    db.close()


@pytest.mark.asyncio
async def test_crawl_stops_on_run_budget():
    db = make_session()
    db.merge(AppSetting(key="max_requests_per_run", value="2"))
    db.merge(AppSetting(key="pages_per_keyword", value="3"))
    db.commit()
    adapter = TikHubAdapter(mock_mode=True)
    run = await run_crawl(db, adapter=adapter)
    assert run.status == "budget_stopped"
    assert run.request_count == 2
    assert run.error_message
    db.close()
