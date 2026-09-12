from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.seed_defaults import get_setting, get_setting_bool, get_setting_float, get_setting_int, set_setting

TWOPLACES = Decimal("0.01")
SAFETY_BUFFER_USD = Decimal("0.50")


def money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass
class ProductBudgetSnapshot:
    crawl_enabled: bool
    mock_mode: bool
    has_token: bool
    free_preview_mode: bool
    preview_used: int
    preview_limit: int
    monthly_budget_usd: Decimal
    usable_budget_usd: Decimal
    estimated_monthly_cost_usd: Decimal
    estimated_run_cost_usd: Decimal
    remaining_usd: Decimal
    results_per_keyword: int
    max_keywords_per_run: int
    within_budget: bool
    can_run: bool
    reason: str | None = None


class ProductBudgetGuard:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self._ensure_billing_month()

    def _ensure_billing_month(self) -> None:
        tz = ZoneInfo(self.settings.scheduler_timezone)
        current_month = datetime.now(tz).strftime("%Y-%m")
        stored = get_setting(self.db, "product_billing_month", "")
        if stored != current_month:
            set_setting(self.db, "product_billing_month", current_month)
            set_setting(self.db, "product_estimated_monthly_cost_usd", "0")
            # Free preview quota is lifetime for the Free plan, not monthly.
            self.db.flush()

    @property
    def crawl_enabled(self) -> bool:
        return get_setting_bool(
            self.db, "product_crawl_enabled", self.settings.product_crawl_enabled
        )

    @property
    def mock_mode(self) -> bool:
        return get_setting_bool(self.db, "product_mock_mode", self.settings.product_mock_mode)

    @property
    def free_preview_mode(self) -> bool:
        return get_setting_bool(
            self.db, "product_free_preview_mode", self.settings.product_free_preview_mode
        )

    @property
    def preview_used(self) -> int:
        return get_setting_int(self.db, "product_free_preview_runs_used", 0)

    @property
    def preview_limit(self) -> int:
        return get_setting_int(
            self.db,
            "product_free_preview_run_limit",
            self.settings.product_free_preview_run_limit,
        )

    @property
    def monthly_budget(self) -> Decimal:
        return money(
            get_setting_float(
                self.db,
                "apify_monthly_budget_usd",
                self.settings.apify_monthly_budget_usd,
            )
        )

    @property
    def price_per_1000(self) -> Decimal:
        return money(
            get_setting_float(
                self.db,
                "apify_estimated_price_per_1000_products",
                self.settings.apify_estimated_price_per_1000_products,
            )
        )

    @property
    def estimated_monthly_cost(self) -> Decimal:
        return money(get_setting(self.db, "product_estimated_monthly_cost_usd", "0") or "0")

    @property
    def results_per_keyword(self) -> int:
        return get_setting_int(
            self.db,
            "product_results_per_keyword",
            self.settings.product_results_per_keyword,
        )

    @property
    def max_keywords_per_run(self) -> int:
        return get_setting_int(
            self.db,
            "product_max_keywords_per_run",
            self.settings.product_max_keywords_per_run,
        )

    def estimate_run_cost(self, max_results: int | None = None) -> Decimal:
        results = max_results if max_results is not None else self.results_per_keyword
        results = max(int(results), 0)
        cost = (Decimal(results) / Decimal(1000)) * self.price_per_1000
        return money(cost)

    def has_token(self) -> bool:
        return bool((self.settings.apify_token or "").strip())

    def validate_run(
        self,
        *,
        keyword_count: int = 1,
        max_results: int | None = None,
        include_details: bool = False,
    ) -> ProductBudgetSnapshot:
        max_results = self.results_per_keyword if max_results is None else int(max_results)
        run_cost = self.estimate_run_cost(max_results)
        monthly = self.estimated_monthly_cost
        budget = self.monthly_budget
        usable = money(budget - SAFETY_BUFFER_USD)
        remaining = money(usable - monthly)
        reason: str | None = None
        can_run = True

        if not self.crawl_enabled:
            can_run = False
            reason = (
                "PRODUCT_CRAWL_ENABLED=false. Đặt true trong .env/cài đặt để bật crawl sản phẩm."
            )
        elif not self.mock_mode and not self.has_token():
            can_run = False
            reason = "Thiếu APIFY_TOKEN khi PRODUCT_MOCK_MODE=false."
        elif self.free_preview_mode and keyword_count > 1:
            can_run = False
            reason = "Free Preview chỉ cho phép 1 từ khóa mỗi lần chạy."
        elif keyword_count > self.max_keywords_per_run:
            can_run = False
            reason = f"Mỗi lần chạy tối đa {self.max_keywords_per_run} từ khóa."
        elif self.free_preview_mode and max_results > 20:
            can_run = False
            reason = "Free Preview không cho maxResults > 20."
        elif max_results > self.results_per_keyword:
            can_run = False
            reason = f"maxResults không được vượt {self.results_per_keyword}."
        elif self.free_preview_mode and include_details:
            can_run = False
            reason = "Free Preview không cho includeDetails=true."
        elif self.free_preview_mode and self.preview_used >= self.preview_limit:
            can_run = False
            reason = (
                f"Đã hết {self.preview_limit} lượt Free Preview "
                f"(đã dùng {self.preview_used})."
            )
        elif monthly + run_cost > usable:
            can_run = False
            reason = (
                f"Chi phí ước tính sẽ vượt ngân sách hữu dụng "
                f"{usable} USD (ngân sách {budget} USD trừ buffer {SAFETY_BUFFER_USD} USD)."
            )

        return ProductBudgetSnapshot(
            crawl_enabled=self.crawl_enabled,
            mock_mode=self.mock_mode,
            has_token=self.has_token(),
            free_preview_mode=self.free_preview_mode,
            preview_used=self.preview_used,
            preview_limit=self.preview_limit,
            monthly_budget_usd=budget,
            usable_budget_usd=usable,
            estimated_monthly_cost_usd=monthly,
            estimated_run_cost_usd=run_cost,
            remaining_usd=remaining if remaining > 0 else money(0),
            results_per_keyword=self.results_per_keyword,
            max_keywords_per_run=self.max_keywords_per_run,
            within_budget=monthly <= usable,
            can_run=can_run,
            reason=reason,
        )

    def record_successful_start(self, run_cost: Decimal) -> None:
        """Increment preview/cost counters only after Actor start succeeds."""
        if self.free_preview_mode:
            set_setting(
                self.db,
                "product_free_preview_runs_used",
                str(self.preview_used + 1),
            )
        new_monthly = money(self.estimated_monthly_cost + money(run_cost))
        set_setting(self.db, "product_estimated_monthly_cost_usd", str(new_monthly))
        self.db.flush()
