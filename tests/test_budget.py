from datetime import datetime

from app.models import AppSetting, CrawlRun
from app.services.budget import BudgetGuard
from tests.conftest import make_session


def test_request_limit_per_run():
    db = make_session()
    db.merge(AppSetting(key="max_requests_per_run", value="2"))
    db.merge(AppSetting(key="max_requests_per_month", value="400"))
    db.commit()
    run = CrawlRun(started_at=datetime.utcnow(), status="running")
    db.add(run)
    db.commit()
    guard = BudgetGuard(db, run)
    assert guard.can_request() is True
    guard.record_search()
    assert guard.can_request() is True
    guard.record_search()
    assert guard.can_request() is False
    assert guard.stopped is True
    assert "lần chạy" in (guard.warning or "")
    db.close()


def test_stop_when_monthly_budget_exceeded():
    db = make_session()
    db.merge(AppSetting(key="max_requests_per_run", value="35"))
    db.merge(AppSetting(key="max_requests_per_month", value="3"))
    db.commit()
    previous = CrawlRun(
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        status="success",
        request_count=3,
        estimated_cost_usd=0.03,
    )
    db.add(previous)
    db.commit()
    run = CrawlRun(started_at=datetime.utcnow(), status="running")
    db.add(run)
    db.commit()
    guard = BudgetGuard(db, run)
    assert guard.month_requests >= 3
    assert guard.can_request() is False
    assert guard.stopped is True
    assert "tháng" in (guard.warning or "")
    db.close()


def test_cost_usd_and_vnd():
    db = make_session()
    db.merge(AppSetting(key="usd_vnd_rate", value="26000"))
    db.merge(AppSetting(key="cost_per_search_usd", value="0.01"))
    db.commit()
    run = CrawlRun(started_at=datetime.utcnow(), status="running")
    db.add(run)
    db.commit()
    guard = BudgetGuard(db, run)
    guard.record_search()
    guard.record_search()
    snap = guard.snapshot()
    assert snap.estimated_cost_usd == 0.02
    assert snap.estimated_cost_vnd == 520
    db.close()
