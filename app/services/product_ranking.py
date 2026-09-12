from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ProductRankResult:
    score: float
    label: str
    components: dict[str, float]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _log_sold_score(monthly_sold: int | None) -> float:
    if monthly_sold is None or monthly_sold <= 0:
        return 0.0
    # log10(1)=0 … log10(100000)≈5 → map to 0–100
    return _clamp((math.log10(monthly_sold + 1) / 5.0) * 100.0)


def _growth_score(
    growth_abs: int | None,
    growth_pct: float | None,
) -> float | None:
    if growth_abs is None and growth_pct is None:
        return None
    abs_part = 0.0
    if growth_abs is not None:
        abs_part = _clamp((math.log10(max(growth_abs, 0) + 1) / 4.0) * 100.0)
    pct_part = 0.0
    if growth_pct is not None:
        pct_part = _clamp(float(growth_pct))
    if growth_abs is None:
        return pct_part
    if growth_pct is None:
        return abs_part
    return _clamp(0.6 * abs_part + 0.4 * pct_part)


def _position_score(search_position: int | None) -> float:
    if search_position is None or search_position <= 0:
        return 40.0
    # position 1 → 100, position 20 → ~20
    return _clamp(100.0 - (search_position - 1) * (80.0 / 19.0))


def _shop_score(shop_score: float | None, review_ratio: float | None) -> float:
    shop = 50.0
    if shop_score is not None:
        # Douyin shop scores often 0–5
        if shop_score <= 5:
            shop = (shop_score / 5.0) * 100.0
        else:
            shop = _clamp(shop_score)
    review = 50.0
    if review_ratio is not None:
        ratio = review_ratio if review_ratio <= 1 else review_ratio / 100.0
        review = _clamp(ratio * 100.0)
    return _clamp(0.6 * shop + 0.4 * review)


def rank_product(
    *,
    relevance_score: float,
    monthly_sold: int | None,
    sales_growth_absolute: int | None,
    sales_growth_percent: float | None,
    search_position: int | None,
    shop_score: float | None,
    good_review_ratio: float | None,
    is_new: bool = False,
) -> ProductRankResult:
    rel = _clamp(float(relevance_score))
    sold = _log_sold_score(monthly_sold)
    growth = _growth_score(sales_growth_absolute, sales_growth_percent)
    pos = _position_score(search_position)
    shop = _shop_score(shop_score, good_review_ratio)

    weights = {
        "relevance": 0.40,
        "sold": 0.25,
        "growth": 0.20,
        "position": 0.10,
        "shop": 0.05,
    }
    components = {
        "relevance": rel,
        "sold": sold,
        "growth": growth if growth is not None else 0.0,
        "position": pos,
        "shop": shop,
    }

    if growth is None:
        # Redistribute growth weight; do not treat missing growth as zero.
        redistributed = {
            "relevance": 0.48,
            "sold": 0.30,
            "position": 0.14,
            "shop": 0.08,
        }
        score = (
            redistributed["relevance"] * rel
            + redistributed["sold"] * sold
            + redistributed["position"] * pos
            + redistributed["shop"] * shop
        )
    else:
        score = (
            weights["relevance"] * rel
            + weights["sold"] * sold
            + weights["growth"] * growth
            + weights["position"] * pos
            + weights["shop"] * shop
        )

    score = round(_clamp(score), 2)

    if is_new or growth is None:
        if rel >= 50:
            label = "mới" if is_new else "thiếu dữ liệu"
        else:
            label = "thiếu dữ liệu"
    elif (sales_growth_percent or 0) >= 30 or (sales_growth_absolute or 0) >= 500:
        label = "tăng nhanh"
    elif (monthly_sold or 0) >= 3000 and rel >= 50:
        label = "bán tốt"
    elif rel >= 50:
        label = "phù hợp"
    else:
        label = "thiếu dữ liệu"

    return ProductRankResult(score=score, label=label, components=components)
