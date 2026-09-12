from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from threading import Lock

from sqlalchemy.orm import Session

from app.apify.adapter import (
    ApifyAdapter,
    ApifyAuthError,
    ApifyBudgetError,
    ApifyTimeoutError,
    ApifyUpstreamError,
)
from app.apify.normalizer import NormalizedProduct
from app.config import Settings, get_settings
from app.models import (
    Product,
    ProductCrawlRun,
    ProductKeyword,
    ProductKeywordLink,
    ProductSnapshot,
)
from app.services.product_budget import ProductBudgetGuard
from app.services.product_relevance import product_relevance

logger = logging.getLogger(__name__)

_keyword_locks: dict[int, Lock] = {}
_keyword_locks_guard = Lock()


class ProductCrawlInProgress(Exception):
    pass


class ProductCrawlBlocked(Exception):
    pass


def _lock_for_keyword(keyword_id: int) -> Lock:
    with _keyword_locks_guard:
        if keyword_id not in _keyword_locks:
            _keyword_locks[keyword_id] = Lock()
        return _keyword_locks[keyword_id]


def upsert_product(
    db: Session,
    item: NormalizedProduct,
    keyword: ProductKeyword | None,
    captured_at: datetime,
    crawl_run: ProductCrawlRun,
) -> tuple[Product, bool, ProductSnapshot]:
    existing = (
        db.query(Product)
        .filter(
            Product.platform == "douyin",
            Product.external_product_id == item.product_id,
        )
        .one_or_none()
    )
    created = False
    if existing is None:
        existing = Product(
            platform="douyin",
            external_product_id=item.product_id,
            promotion_id=item.promotion_id or "",
            title=item.title or "",
            product_url=item.product_url or "",
            main_image_url=item.main_image_url or "",
            shop_id=item.shop_id or "",
            shop_name=item.shop_name or "",
            category_name=item.category_name or "",
            first_seen_at=captured_at,
            last_seen_at=captured_at,
            raw_json=item.raw_json,
        )
        db.add(existing)
        db.flush()
        created = True
    else:
        existing.promotion_id = item.promotion_id or existing.promotion_id
        existing.title = item.title or existing.title
        existing.product_url = item.product_url or existing.product_url
        existing.main_image_url = item.main_image_url or existing.main_image_url
        existing.shop_id = item.shop_id or existing.shop_id
        existing.shop_name = item.shop_name or existing.shop_name
        existing.category_name = item.category_name or existing.category_name
        existing.last_seen_at = captured_at
        existing.raw_json = item.raw_json or existing.raw_json

    if keyword is not None:
        link = (
            db.query(ProductKeywordLink)
            .filter(
                ProductKeywordLink.product_id == existing.id,
                ProductKeywordLink.keyword_id == keyword.id,
            )
            .one_or_none()
        )
        if link is None:
            db.add(
                ProductKeywordLink(
                    product_id=existing.id,
                    keyword_id=keyword.id,
                    first_seen_at=captured_at,
                    last_seen_at=captured_at,
                    best_search_position=item.search_position,
                )
            )
        else:
            link.last_seen_at = captured_at
            if item.search_position is not None:
                if (
                    link.best_search_position is None
                    or item.search_position < link.best_search_position
                ):
                    link.best_search_position = item.search_position

    previous = (
        db.query(ProductSnapshot)
        .filter(ProductSnapshot.product_id == existing.id)
        .order_by(ProductSnapshot.captured_at.desc(), ProductSnapshot.id.desc())
        .first()
    )
    growth_abs: int | None = None
    growth_pct: float | None = None
    if previous is not None and item.monthly_sold is not None and previous.monthly_sold is not None:
        growth_abs = int(item.monthly_sold) - int(previous.monthly_sold)
        if previous.monthly_sold > 0:
            growth_pct = round((growth_abs / previous.monthly_sold) * 100.0, 2)
        elif growth_abs > 0:
            growth_pct = 100.0

    same_run = (
        db.query(ProductSnapshot)
        .filter(
            ProductSnapshot.product_id == existing.id,
            ProductSnapshot.crawl_run_id == crawl_run.id,
        )
        .one_or_none()
    )
    if same_run is not None:
        same_run.captured_at = captured_at
        same_run.price_cny = item.price_cny
        same_run.monthly_sold = item.monthly_sold
        same_run.lifetime_sold = item.lifetime_sold
        same_run.good_review_ratio = item.good_review_ratio
        same_run.shop_score = item.shop_score
        same_run.creator_count = item.creator_count
        same_run.commission_rate = item.commission_rate
        same_run.search_position = item.search_position
        same_run.sales_growth_absolute = growth_abs
        same_run.sales_growth_percent = growth_pct
        snapshot = same_run
    else:
        snapshot = ProductSnapshot(
            product_id=existing.id,
            crawl_run_id=crawl_run.id,
            captured_at=captured_at,
            price_cny=item.price_cny,
            monthly_sold=item.monthly_sold,
            lifetime_sold=item.lifetime_sold,
            good_review_ratio=item.good_review_ratio,
            shop_score=item.shop_score,
            creator_count=item.creator_count,
            commission_rate=item.commission_rate,
            search_position=item.search_position,
            sales_growth_absolute=growth_abs,
            sales_growth_percent=growth_pct,
        )
        db.add(snapshot)
        db.flush()

    return existing, created, snapshot


async def run_product_crawl(
    db: Session,
    keyword_id: int,
    *,
    settings: Settings | None = None,
    adapter: ApifyAdapter | None = None,
) -> ProductCrawlRun:
    settings = settings or get_settings()
    keyword = db.get(ProductKeyword, keyword_id)
    if keyword is None:
        raise ProductCrawlBlocked(f"Không tìm thấy từ khóa sản phẩm id={keyword_id}.")
    if not keyword.enabled:
        raise ProductCrawlBlocked(f"Từ khóa «{keyword.keyword}» đang tắt.")

    lock = _lock_for_keyword(keyword_id)
    if not lock.acquire(blocking=False):
        raise ProductCrawlInProgress(f"Từ khóa «{keyword.keyword}» đang được crawl.")

    owns_adapter = adapter is None
    run: ProductCrawlRun | None = None
    try:
        budget = ProductBudgetGuard(db)
        check = budget.validate_run(keyword_count=1, include_details=False)
        if not check.can_run:
            raise ProductCrawlBlocked(check.reason or "Crawl sản phẩm bị chặn.")

        run = ProductCrawlRun(
            keyword_id=keyword.id,
            status="running",
            started_at=datetime.utcnow(),
            requested_limit=check.results_per_keyword,
            estimated_cost_usd=float(check.estimated_run_cost_usd),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        adapter = adapter or ApifyAdapter(
            settings=settings,
            mock_mode=check.mock_mode,
        )
        try:
            # Count preview/cost only after Actor start succeeds (before wait/fetch).
            if check.mock_mode:
                result = await adapter.search_products(
                    keyword.keyword,
                    max_results=check.results_per_keyword,
                    include_details=False,
                )
                budget.record_successful_start(Decimal(str(check.estimated_run_cost_usd)))
            else:
                start_payload = await adapter.start_run(
                    keyword.keyword,
                    max_results=check.results_per_keyword,
                    include_details=False,
                )
                budget.record_successful_start(Decimal(str(check.estimated_run_cost_usd)))
                run_data = start_payload.get("data") or {}
                run_id = str(run_data.get("id") or "")
                dataset_id = str(run_data.get("defaultDatasetId") or "")
                run.apify_run_id = run_id or None
                run.apify_dataset_id = dataset_id or None
                db.commit()
                finished = await adapter.wait_for_run(run_id)
                status = str((finished.get("data") or {}).get("status") or "")
                dataset_id = str(
                    (finished.get("data") or {}).get("defaultDatasetId") or dataset_id
                )
                if status.upper() != "SUCCEEDED":
                    raise ApifyUpstreamError(
                        f"Apify run kết thúc với trạng thái {status or 'unknown'}"
                    )
                raw_items = await adapter.fetch_dataset_items(dataset_id)
                from app.apify.normalizer import normalize_dataset_items
                from app.apify.adapter import ApifyRunResult

                items = normalize_dataset_items(raw_items, keyword=keyword.keyword)[
                    : check.results_per_keyword
                ]
                result = ApifyRunResult(
                    run_id=run_id,
                    dataset_id=dataset_id,
                    status=status,
                    items=items,
                    raw_items=raw_items,
                )
            run.apify_run_id = result.run_id
            run.apify_dataset_id = result.dataset_id
            run.received_count = len(result.raw_items)
            run.normalized_count = len(result.items)
            run.estimated_cost_usd = float(check.estimated_run_cost_usd)
            db.commit()

            captured_at = datetime.utcnow()
            seen_ids: set[str] = set()
            accepted = 0
            rejected = 0
            new_count = 0
            duplicates = 0

            for item in result.items:
                if item.product_id in seen_ids:
                    duplicates += 1
                    continue
                seen_ids.add(item.product_id)

                relevance = product_relevance(
                    item.title,
                    category_name=item.category_name,
                    shop_name=item.shop_name,
                )
                if not relevance.accepted:
                    rejected += 1
                    logger.info(
                        "Reject product id=%s title=%s reasons=%s",
                        item.product_id,
                        (item.title or "")[:80],
                        "; ".join(relevance.reasons),
                    )
                    continue

                _product, created, _snapshot = upsert_product(
                    db, item, keyword, captured_at, run
                )
                accepted += 1
                if created:
                    new_count += 1
                else:
                    duplicates += 1

            run.accepted_count = accepted
            run.rejected_count = rejected
            run.new_product_count = new_count
            run.duplicate_count = duplicates
            run.status = "success"
            run.finished_at = datetime.utcnow()
            db.commit()

            logger.info(
                "Product crawl done keyword=%s run_id=%s dataset=%s received=%s "
                "normalized=%s accepted=%s rejected=%s new=%s dup=%s cost_usd=%s",
                keyword.keyword,
                run.apify_run_id,
                run.apify_dataset_id,
                run.received_count,
                run.normalized_count,
                run.accepted_count,
                run.rejected_count,
                run.new_product_count,
                run.duplicate_count,
                run.estimated_cost_usd,
            )
            return run
        except (ApifyAuthError, ApifyBudgetError, ApifyTimeoutError, ApifyUpstreamError) as exc:
            run.status = "error"
            run.error_message = str(exc)
            run.finished_at = datetime.utcnow()
            run.apify_run_id = adapter.last_run_id
            run.apify_dataset_id = adapter.last_dataset_id
            db.commit()
            logger.error(
                "Product crawl failed keyword=%s reason=%s",
                keyword.keyword,
                str(exc),
            )
            return run
        finally:
            if owns_adapter and adapter is not None:
                await adapter.aclose()
    except Exception:
        if run is not None and run.status == "running":
            run.status = "error"
            run.error_message = "Lỗi không xác định khi crawl sản phẩm."
            run.finished_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        lock.release()
