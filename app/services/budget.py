from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import CrawlRun
from app.services.seed_defaults import get_setting_float, get_setting_int


def month_bounds(now: datetime | None = None, timezone_name: str = "Asia/Bangkok") -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name)
    current = (now or datetime.now(tz)).astimezone(tz)
    start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.replace(tzinfo=None), end.replace(tzinfo=None)


def monthly_request_count(db: Session, timezone_name: str = "Asia/Bangkok") -> int:
    start, end = month_bounds(timezone_name=timezone_name)
    total = (
        db.query(func.coalesce(func.sum(CrawlRun.request_count), 0))
        .filter(CrawlRun.started_at >= start, CrawlRun.started_at < end)
        .scalar()
    )
    return int(total or 0)


@dataclass
class BudgetSnapshot:
    run_requests: int
    month_requests: int
    max_run: int
    max_month: int
    estimated_cost_usd: float
    estimated_cost_vnd: float
    usd_vnd_rate: float
    within_budget: bool
    stopped: bool
    warning: str | None = None


class BudgetGuard:
    def __init__(self, db: Session, run: CrawlRun | None = None) -> None:
        self.db = db
        self.run = run
        self.run_requests = run.request_count if run else 0
        self.month_requests = monthly_request_count(db)
        self.max_run = get_setting_int(db, "max_requests_per_run", 35)
        self.max_month = get_setting_int(db, "max_requests_per_month", 400)
        self.cost_search = get_setting_float(db, "cost_per_search_usd", 0.01)
        self.cost_stats = get_setting_float(db, "cost_per_stats_usd", 0.025)
        self.usd_vnd_rate = get_setting_float(db, "usd_vnd_rate", 26000)
        self.search_count = 0
        self.stats_count = 0
        self.stopped = False
        self.warning: str | None = None

    @property
    def estimated_cost_usd(self) -> float:
        return round(self.search_count * self.cost_search + self.stats_count * self.cost_stats, 6)

    def remaining_run(self) -> int:
        return max(self.max_run - self.run_requests, 0)

    def remaining_month(self) -> int:
        return max(self.max_month - self.month_requests, 0)

    def remaining(self) -> int:
        return min(self.remaining_run(), self.remaining_month())

    def can_request(self, count: int = 1) -> bool:
        if self.stopped:
            return False
        if self.run_requests + count > self.max_run:
            self._stop(f"Sắp vượt giới hạn {self.max_run} request/lần chạy.")
            return False
        if self.month_requests + count > self.max_month:
            self._stop(f"Sắp vượt giới hạn {self.max_month} request/tháng.")
            return False
        return True

    def record_search(self) -> None:
        self._record(kind="search")

    def record_stats(self) -> None:
        self._record(kind="stats")

    def _record(self, kind: str) -> None:
        self.run_requests += 1
        self.month_requests += 1
        if kind == "search":
            self.search_count += 1
        else:
            self.stats_count += 1
        if self.run is not None:
            self.run.request_count = self.run_requests
            self.run.estimated_cost_usd = self.estimated_cost_usd

    def _stop(self, message: str) -> None:
        self.stopped = True
        self.warning = message
        if self.run is not None:
            self.run.error_message = message

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            run_requests=self.run_requests,
            month_requests=self.month_requests,
            max_run=self.max_run,
            max_month=self.max_month,
            estimated_cost_usd=self.estimated_cost_usd,
            estimated_cost_vnd=round(self.estimated_cost_usd * self.usd_vnd_rate, 0),
            usd_vnd_rate=self.usd_vnd_rate,
            within_budget=not self.stopped,
            stopped=self.stopped,
            warning=self.warning,
        )
