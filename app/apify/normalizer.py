from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


SOLD_RE = re.compile(
    r"(?:已售)?\s*([0-9]+(?:\.[0-9]+)?)\s*([万wWkK]?)\s*\+?",
    re.IGNORECASE,
)


@dataclass
class NormalizedProduct:
    product_id: str
    promotion_id: str = ""
    title: str = ""
    product_url: str = ""
    main_image_url: str = ""
    price_cny: float | None = None
    monthly_sold: int | None = None
    lifetime_sold: int | None = None
    good_review_ratio: float | None = None
    shop_id: str = ""
    shop_name: str = ""
    shop_score: float | None = None
    creator_count: int | None = None
    commission_rate: float | None = None
    keyword: str = ""
    search_position: int | None = None
    category_name: str = ""
    raw_json: dict[str, Any] = field(default_factory=dict)


def nested_get(obj: Any, *paths: str, default: Any = None) -> Any:
    for path in paths:
        current = obj
        found = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
    return default


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_sold_count(value: Any) -> int | None:
    """Parse sold counts such as 5000, '5000+', '已售5000+', '1万+', '1.2万'."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = str(value).strip().replace(",", "")
    direct = parse_int(text.rstrip("+"))
    if direct is not None and "万" not in text and not re.search(r"[wWkK]", text):
        return direct
    match = SOLD_RE.search(text)
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    if unit in {"万", "w"}:
        number *= 10000
    elif unit == "k":
        number *= 1000
    return int(number)


def parse_price_cny(value: Any) -> float | None:
    """Accept CNY floats or integer cents (>= 100 and looks like cents)."""
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        for key in ("min", "max", "price", "amount", "value"):
            if key in value:
                parsed = parse_price_cny(value[key])
                if parsed is not None:
                    return parsed
        return None
    text = str(value).strip().lower().replace("¥", "").replace("￥", "").replace(",", "")
    text = text.replace("cny", "").replace("元", "").strip()
    number = parse_float(text)
    if number is None:
        return None
    # Heuristic: large integers without decimal often mean fen/cents.
    if isinstance(value, int) or (isinstance(value, str) and "." not in text):
        if number >= 1000 and number == int(number):
            return round(number / 100.0, 2)
    return round(number, 2)


def first_url(value: Any) -> str:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, dict):
        for key in ("url", "uri", "src"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                return candidate
        urls = value.get("url_list") or value.get("urlList") or []
        if isinstance(urls, list) and urls:
            return first_url(urls[0])
    if isinstance(value, list) and value:
        return first_url(value[0])
    return ""


def truncate_raw(raw: dict[str, Any], max_chars: int = 8000) -> dict[str, Any]:
    """Keep raw payload for DB but avoid huge nested blobs in memory dumps."""
    try:
        import json

        encoded = json.dumps(raw, ensure_ascii=False)
        if len(encoded) <= max_chars:
            return raw
        return {"_truncated": True, "preview": encoded[:max_chars]}
    except Exception:
        return {"_truncated": True}


def normalize_product_item(
    item: dict[str, Any],
    *,
    keyword: str = "",
    search_position: int | None = None,
) -> NormalizedProduct | None:
    if not isinstance(item, dict):
        return None
    product_id = nested_get(
        item,
        "productId",
        "product_id",
        "id",
        "goods_id",
        "goodsId",
        "product_info.product_id",
        "product_info.productId",
    )
    product_id = str(product_id).strip() if product_id is not None else ""
    if not product_id:
        return None

    title = str(
        nested_get(item, "title", "name", "product_name", "productName", "product_title") or ""
    ).strip()
    product_url = str(
        nested_get(
            item,
            "product_url",
            "productUrl",
            "url",
            "detail_url",
            "detailUrl",
            "share_url",
        )
        or ""
    ).strip()
    if product_url and not product_url.startswith(("http://", "https://")):
        product_url = f"https://haohuo.jinritemai.com/ecommerce/trade/detail/index.html?id={product_id}"

    image = first_url(
        nested_get(
            item,
            "main_image_url",
            "mainImageUrl",
            "cover",
            "image",
            "img",
            "main_image",
            "mainImage",
            "images",
        )
    )

    price = parse_price_cny(
        nested_get(
            item,
            "price_cny",
            "priceCny",
            "price",
            "min_price",
            "minPrice",
            "sale_price",
            "salePrice",
            "sku_price",
        )
    )
    monthly_sold = parse_sold_count(
        nested_get(
            item,
            "monthly_sold",
            "monthlySold",
            "sales",
            "sold_count",
            "soldCount",
            "sell_num",
            "sellNum",
            "sales_volume",
            "month_sales",
            "monthSales",
        )
    )
    lifetime_sold = parse_sold_count(
        nested_get(
            item,
            "lifetime_sold",
            "lifetimeSold",
            "total_sold",
            "totalSold",
            "total_sales",
            "totalSales",
        )
    )
    review = parse_float(
        nested_get(
            item,
            "good_review_ratio",
            "goodReviewRatio",
            "good_ratio",
            "positive_ratio",
            "comment_good_ratio",
        )
    )
    if review is not None and review > 1:
        review = review / 100.0

    shop_id = str(
        nested_get(item, "shop_id", "shopId", "shop.id", "shop_info.shop_id") or ""
    ).strip()
    shop_name = str(
        nested_get(
            item,
            "shop_name",
            "shopName",
            "shop.name",
            "shop_info.shop_name",
            "store_name",
        )
        or ""
    ).strip()
    shop_score = parse_float(
        nested_get(item, "shop_score", "shopScore", "shop.score", "shop_info.score")
    )
    creator_count = parse_int(
        nested_get(item, "creator_count", "creatorCount", "author_count", "kol_count")
    )
    commission = parse_float(
        nested_get(item, "commission_rate", "commissionRate", "cos_ratio", "cosRatio")
    )
    if commission is not None and commission > 1:
        commission = commission / 100.0

    category = str(
        nested_get(item, "category_name", "categoryName", "category", "cid_name") or ""
    ).strip()
    promotion_id = str(
        nested_get(item, "promotion_id", "promotionId", "prom_id") or ""
    ).strip()
    position = parse_int(
        nested_get(item, "search_position", "searchPosition", "rank", "position")
    )
    if position is None:
        position = search_position
    kw = str(nested_get(item, "keyword", "search_keyword") or keyword or "").strip()

    return NormalizedProduct(
        product_id=product_id,
        promotion_id=promotion_id,
        title=title,
        product_url=product_url
        or f"https://haohuo.jinritemai.com/ecommerce/trade/detail/index.html?id={product_id}",
        main_image_url=image,
        price_cny=price,
        monthly_sold=monthly_sold,
        lifetime_sold=lifetime_sold,
        good_review_ratio=review,
        shop_id=shop_id,
        shop_name=shop_name,
        shop_score=shop_score,
        creator_count=creator_count,
        commission_rate=commission,
        keyword=kw,
        search_position=position,
        category_name=category,
        raw_json=truncate_raw(item),
    )


def normalize_dataset_items(
    items: list[Any],
    *,
    keyword: str = "",
) -> list[NormalizedProduct]:
    products: list[NormalizedProduct] = []
    for index, item in enumerate(items or [], start=1):
        if not isinstance(item, dict):
            continue
        normalized = normalize_product_item(item, keyword=keyword, search_position=index)
        if normalized is not None:
            products.append(normalized)
    return products
