from __future__ import annotations

from typing import Any


def mock_actor_run_start(keyword: str) -> dict[str, Any]:
    return {
        "data": {
            "id": f"mock-run-{keyword}",
            "actId": "zen-studio~douyin-product-search-scraper",
            "status": "RUNNING",
            "defaultDatasetId": f"mock-dataset-{keyword}",
        }
    }


def mock_actor_run_finished(run_id: str, dataset_id: str) -> dict[str, Any]:
    return {
        "data": {
            "id": run_id,
            "status": "SUCCEEDED",
            "defaultDatasetId": dataset_id,
        }
    }


def mock_dataset_items(keyword: str) -> list[dict[str, Any]]:
    """Diverse fixtures covering relevance, sold formats, missing fields, and overlaps."""
    shared = {
        "productId": "shared-party-001",
        "title": "法式收腰连衣裙宴会小礼服显瘦",
        "price": "129.9",
        "monthly_sold": "3200+",
        "shop_name": "Tisora风格店",
        "shop_score": 4.8,
        "good_review_ratio": 0.96,
        "category_name": "连衣裙",
        "productUrl": "https://haohuo.jinritemai.com/ecommerce/trade/detail/index.html?id=shared-party-001",
        "main_image_url": "https://example.com/shared.jpg",
        "keyword": keyword,
    }
    base = [
        {
            "productId": "party-dress-001",
            "title": "法式收腰连衣裙女宴会生日小礼服",
            "price": 15900,  # cents
            "monthlySold": "1万+",
            "shopId": "shop-1",
            "shopName": "派对裙旗舰店",
            "shopScore": "4.9",
            "goodReviewRatio": "98%",
            "creatorCount": 12,
            "commissionRate": 0.15,
            "categoryName": "连衣裙",
            "mainImageUrl": "https://example.com/party1.jpg",
            "productUrl": "https://haohuo.jinritemai.com/ecommerce/trade/detail/index.html?id=party-dress-001",
        },
        {
            "product_id": "bridesmaid-002",
            "title": "伴娘裙宴会小礼服显瘦收腰",
            "price_cny": "199.5",
            "sales": "已售5000+",
            "shop_name": "伴娘优选",
            "shop_score": 4.7,
            "good_review_ratio": 0.94,
            "category_name": "礼服",
            "main_image_url": "https://example.com/bridesmaid.jpg",
        },
        {
            "productId": "wedding-003",
            "title": "新娘主纱婚纱敬酒服新娘",
            "price": "899",
            "monthly_sold": 800,
            "shop_name": "婚纱馆",
            "category_name": "婚纱",
            "main_image_url": "https://example.com/wedding.jpg",
        },
        {
            "productId": "kids-004",
            "title": "儿童童装公主连衣裙",
            "price": "89",
            "sold_count": "1200",
            "shop_name": "童装店",
            "category_name": "童装",
        },
        {
            "id": "hanfu-005",
            "title": "汉服古装女装套装",
            "price": "259",
            "month_sales": "900",
            "shop_name": "汉服坊",
            "category_name": "汉服",
        },
        {
            "productId": "missing-006",
            # intentionally sparse fields
            "name": "一字肩收腰连衣裙显瘦",
            "price": "88.0",
        },
        {
            "productId": "wan-sold-007",
            "title": "方领蓬蓬连衣裙生日约会",
            "min_price": "168",
            "sell_num": "1.2万+",
            "shop_name": "蓬蓬裙店",
            "shop_score": 4.6,
            "category_name": "连衣裙",
            "main_image_url": "https://example.com/puff.jpg",
        },
        {
            "productId": "growth-008",
            "title": "斜肩花苞小礼服显瘦收腰",
            "price": "219",
            "monthly_sold": 1500,
            "shop_name": "花苞裙店",
            "shop_score": 4.85,
            "good_review_ratio": 0.97,
            "category_name": "礼服",
            "main_image_url": "https://example.com/growth.jpg",
        },
        {
            "productId": "new-009",
            "title": "黑色丝绒抹胸蝴蝶结生日连衣裙",
            "price": "289",
            "monthly_sold": 120,
            "shop_name": "丝绒裙店",
            "category_name": "连衣裙",
            "main_image_url": "https://example.com/new.jpg",
        },
        shared,
    ]
    # Second keyword gets the shared product again for overlap tests.
    if "一字肩" in keyword or keyword.endswith("2"):
        base.append(dict(shared, keyword=keyword, search_position=1))
    for index, item in enumerate(base, start=1):
        item.setdefault("keyword", keyword)
        item.setdefault("search_position", index)
    return base


def mock_growth_dataset_items(keyword: str) -> list[dict[str, Any]]:
    """Second-run fixtures with higher sold counts for growth tests."""
    items = mock_dataset_items(keyword)
    for item in items:
        pid = str(item.get("productId") or item.get("product_id") or item.get("id") or "")
        if pid == "growth-008":
            item["monthly_sold"] = 2800
        if pid == "party-dress-001":
            item["monthlySold"] = "1.5万+"
        if pid == "shared-party-001":
            item["monthly_sold"] = "4500+"
    return items
