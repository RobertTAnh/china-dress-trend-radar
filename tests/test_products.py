from __future__ import annotations

import logging

import httpx
import pytest
import respx
from httpx import Response

from app.apify.adapter import (
    ApifyAdapter,
    ApifyAuthError,
    ApifyBudgetError,
    ApifyTimeoutError,
    ApifyUpstreamError,
)
from app.apify.mock_fixtures import mock_dataset_items, mock_growth_dataset_items
from app.apify.normalizer import (
    normalize_dataset_items,
    normalize_product_item,
    parse_price_cny,
    parse_sold_count,
)
from app.config import Settings
from app.logging_utils import RedactFilter, redact_secrets
from app.models import Product, ProductKeyword, ProductSnapshot
from app.services.product_budget import ProductBudgetGuard
from app.services.product_crawler import (
    ProductCrawlBlocked,
    run_product_crawl,
    upsert_product,
)
from app.services.product_ranking import rank_product
from app.services.product_relevance import product_relevance
from app.services.seed_defaults import set_setting
from app.apify.normalizer import NormalizedProduct
from datetime import datetime

from tests.conftest import make_session


def test_parse_sold_formats():
    assert parse_sold_count("1万+") == 10000
    assert parse_sold_count("已售5000+") == 5000
    assert parse_sold_count("1.2万") == 12000
    assert parse_sold_count(3200) == 3200
    assert parse_sold_count(None) is None


def test_parse_price_cny_and_cents():
    assert parse_price_cny(15900) == 159.0
    assert parse_price_cny("129.9") == 129.9
    assert parse_price_cny("¥88") == 88.0


def test_normalize_missing_and_aliases():
    item = normalize_product_item(
        {"productId": "x1", "name": "法式收腰连衣裙", "price": "88.0"},
        keyword="法式收腰连衣裙",
        search_position=3,
    )
    assert item is not None
    assert item.product_id == "x1"
    assert item.title == "法式收腰连衣裙"
    assert item.price_cny == 88.0
    assert item.search_position == 3


def test_normalize_dataset_mock_fixtures():
    items = normalize_dataset_items(mock_dataset_items("法式收腰连衣裙"), keyword="法式收腰连衣裙")
    ids = {p.product_id for p in items}
    assert "party-dress-001" in ids
    assert "bridesmaid-002" in ids
    party = next(p for p in items if p.product_id == "party-dress-001")
    assert party.monthly_sold == 10000
    assert party.price_cny == 159.0


def test_relevance_keeps_bridesmaid_rejects_wedding_kids_hanfu():
    ok = product_relevance("伴娘裙宴会小礼服显瘦收腰")
    assert ok.accepted
    assert ok.score >= 50

    wedding = product_relevance("新娘主纱婚纱敬酒服新娘")
    assert not wedding.accepted

    kids = product_relevance("儿童童装公主连衣裙", category_name="童装")
    assert not kids.accepted

    hanfu = product_relevance("汉服古装女装套装")
    assert not hanfu.accepted

    party = product_relevance("法式收腰连衣裙女宴会生日小礼服")
    assert party.accepted

    bodycon = product_relevance("收腰显瘦包臀连衣裙女")
    assert bodycon.accepted

    handbag = product_relevance("法式女包手提包")
    assert not handbag.accepted


def test_ranking_redistributes_without_growth():
    with_growth = rank_product(
        relevance_score=80,
        monthly_sold=5000,
        sales_growth_absolute=800,
        sales_growth_percent=40,
        search_position=2,
        shop_score=4.8,
        good_review_ratio=0.96,
        is_new=False,
    )
    no_growth = rank_product(
        relevance_score=80,
        monthly_sold=5000,
        sales_growth_absolute=None,
        sales_growth_percent=None,
        search_position=2,
        shop_score=4.8,
        good_review_ratio=0.96,
        is_new=True,
    )
    assert with_growth.label == "tăng nhanh"
    assert no_growth.label in {"mới", "thiếu dữ liệu"}
    assert 0 <= no_growth.score <= 100


def test_upsert_dedupe_and_growth():
    db = make_session()
    kw = db.query(ProductKeyword).first()
    assert kw is not None
    from app.models import ProductCrawlRun

    run1 = ProductCrawlRun(keyword_id=kw.id, status="running", requested_limit=20)
    db.add(run1)
    db.flush()
    item = NormalizedProduct(
        product_id="growth-008",
        title="斜肩花苞小礼服显瘦收腰",
        price_cny=219,
        monthly_sold=1500,
        shop_name="花苞裙店",
        category_name="礼服",
        search_position=1,
    )
    p1, created1, snap1 = upsert_product(db, item, kw, datetime.utcnow(), run1)
    assert created1
    assert snap1.sales_growth_absolute is None
    db.commit()

    run2 = ProductCrawlRun(keyword_id=kw.id, status="running", requested_limit=20)
    db.add(run2)
    db.flush()
    item.monthly_sold = 2800
    p2, created2, snap2 = upsert_product(db, item, kw, datetime.utcnow(), run2)
    assert not created2
    assert p2.id == p1.id
    assert snap2.sales_growth_absolute == 1300
    assert db.query(Product).count() == 1
    assert db.query(ProductSnapshot).count() == 2


@pytest.mark.asyncio
async def test_product_crawl_mock_and_budget_counters():
    db = make_session()
    set_setting(db, "product_crawl_enabled", "true")
    set_setting(db, "product_mock_mode", "true")
    set_setting(db, "product_free_preview_runs_used", "0")
    set_setting(db, "product_estimated_monthly_cost_usd", "0")
    db.commit()
    kw = db.query(ProductKeyword).filter(ProductKeyword.enabled.is_(True)).first()
    run = await run_product_crawl(db, kw.id)
    assert run.status == "success"
    assert run.received_count > 0
    assert run.accepted_count >= 1
    assert run.rejected_count >= 1
    assert db.query(Product).count() >= 1
    budget = ProductBudgetGuard(db)
    assert budget.preview_used == 1
    assert float(budget.estimated_monthly_cost) > 0


def test_budget_blocks_disabled_missing_token_preview_and_overspend():
    db = make_session()
    guard = ProductBudgetGuard(db)
    set_setting(db, "product_crawl_enabled", "false")
    db.commit()
    assert not guard.validate_run().can_run

    set_setting(db, "product_crawl_enabled", "true")
    set_setting(db, "product_mock_mode", "false")
    db.commit()
    settings = get_settings_override(apify_token="")
    guard.settings = settings
    snap = guard.validate_run()
    assert not snap.can_run
    assert "APIFY_TOKEN" in (snap.reason or "")

    set_setting(db, "product_mock_mode", "true")
    set_setting(db, "product_free_preview_runs_used", "10")
    db.commit()
    snap = ProductBudgetGuard(db).validate_run()
    assert not snap.can_run
    assert "Free Preview" in (snap.reason or "")

    set_setting(db, "product_free_preview_runs_used", "0")
    set_setting(db, "product_estimated_monthly_cost_usd", "3.95")
    db.commit()
    snap = ProductBudgetGuard(db).validate_run()
    # usable = 4.50 - 0.50 = 4.00; 3.95 + ~0.16 > 4.00
    assert not snap.can_run

    snap_multi = ProductBudgetGuard(db).validate_run(keyword_count=2)
    assert not snap_multi.can_run


def get_settings_override(**kwargs) -> Settings:
    base = Settings(
        product_mock_mode=True,
        product_crawl_enabled=True,
        apify_token=kwargs.get("apify_token", "test-token"),
    )
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


@pytest.mark.asyncio
@respx.mock
async def test_apify_adapter_http_flow_retry_and_auth():
    settings = get_settings_override(product_mock_mode=False, apify_token="secret-token")
    route_start = respx.post("https://api.apify.com/v2/acts/zen-studio~douyin-product-search-scraper/runs").mock(
        side_effect=[
            Response(500, json={"error": "temp"}),
            Response(
                201,
                json={
                    "data": {
                        "id": "run-1",
                        "status": "RUNNING",
                        "defaultDatasetId": "ds-1",
                    }
                },
            ),
        ]
    )
    respx.get("https://api.apify.com/v2/actor-runs/run-1").mock(
        return_value=Response(
            200,
            json={"data": {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "ds-1"}},
        )
    )
    respx.get("https://api.apify.com/v2/datasets/ds-1/items").mock(
        return_value=Response(200, json=mock_dataset_items("法式收腰连衣裙")[:3])
    )
    async with httpx.AsyncClient(base_url="https://api.apify.com") as client:
        adapter = ApifyAdapter(settings=settings, client=client, mock_mode=False)
        result = await adapter.search_products("法式收腰连衣裙", max_results=3)
    assert result.run_id == "run-1"
    assert len(result.items) >= 1
    assert route_start.call_count == 2

    respx.clear()
    respx.post("https://api.apify.com/v2/acts/zen-studio~douyin-product-search-scraper/runs").mock(
        return_value=Response(401, json={"error": "unauthorized"})
    )
    async with httpx.AsyncClient(base_url="https://api.apify.com") as client:
        adapter = ApifyAdapter(settings=settings, client=client, mock_mode=False)
        with pytest.raises(ApifyAuthError):
            await adapter.start_run("法式收腰连衣裙")


@pytest.mark.asyncio
@respx.mock
async def test_apify_timeout_and_budget_error():
    settings = get_settings_override(
        product_mock_mode=False,
        apify_token="secret-token",
        apify_run_timeout_seconds=0.01,
        apify_poll_interval_seconds=0.01,
    )
    respx.get("https://api.apify.com/v2/actor-runs/run-slow").mock(
        return_value=Response(
            200,
            json={"data": {"id": "run-slow", "status": "RUNNING", "defaultDatasetId": "ds"}},
        )
    )
    async with httpx.AsyncClient(base_url="https://api.apify.com") as client:
        adapter = ApifyAdapter(settings=settings, client=client, mock_mode=False)
        with pytest.raises(ApifyTimeoutError):
            await adapter.wait_for_run("run-slow")

    respx.clear()
    respx.post("https://api.apify.com/v2/acts/zen-studio~douyin-product-search-scraper/runs").mock(
        return_value=Response(402, text="insufficient credit")
    )
    async with httpx.AsyncClient(base_url="https://api.apify.com") as client:
        adapter = ApifyAdapter(settings=settings, client=client, mock_mode=False)
        with pytest.raises(ApifyBudgetError):
            await adapter.start_run("法式收腰连衣裙")


def test_token_redacted_from_logs(caplog):
    logger = logging.getLogger("test_apify_redact")
    logger.addFilter(RedactFilter())
    logger.setLevel(logging.INFO)
    with caplog.at_level(logging.INFO, logger="test_apify_redact"):
        logger.info("Authorization Bearer secret-token-xyz APIFY_TOKEN=abc123token")
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "secret-token-xyz" not in joined
    assert "abc123token" not in joined
    assert "[REDACTED]" in joined
    assert "abc123token" not in redact_secrets("APIFY_TOKEN=abc123token")


@pytest.mark.asyncio
async def test_crawl_blocked_when_disabled():
    db = make_session()
    set_setting(db, "product_crawl_enabled", "false")
    db.commit()
    kw = db.query(ProductKeyword).first()
    with pytest.raises(ProductCrawlBlocked):
        await run_product_crawl(db, kw.id)


def test_growth_fixture_increases_sold():
    first = {i["productId"]: i for i in mock_dataset_items("k") if "productId" in i}
    second = {i["productId"]: i for i in mock_growth_dataset_items("k") if "productId" in i}
    assert second["growth-008"]["monthly_sold"] > first["growth-008"]["monthly_sold"]
