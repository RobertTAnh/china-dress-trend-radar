from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, joinedload

from app.models import Product, ProductKeywordLink, ProductSnapshot
from app.services.product_ranking import rank_product
from app.services.product_relevance import product_relevance


@dataclass
class ProductCard:
    product: Product
    snapshot: ProductSnapshot | None
    relevance_score: int
    relevance_reasons: list[str]
    rank_score: float
    rank_label: str
    keywords: list[str]
    is_new: bool
    is_fast_growth: bool


def _latest_snapshot(product: Product) -> ProductSnapshot | None:
    if not product.snapshots:
        return None
    return max(product.snapshots, key=lambda s: (s.captured_at, s.id))


def load_product_cards(
    db: Session,
    *,
    keyword_id: int | None = None,
    only_relevant: bool = False,
    only_new: bool = False,
    only_fast_growth: bool = False,
    min_sold: int | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = "rank_score",
    limit: int | None = None,
) -> list[ProductCard]:
    query = db.query(Product).options(
        joinedload(Product.snapshots),
        joinedload(Product.keywords).joinedload(ProductKeywordLink.keyword),
    )
    if keyword_id is not None:
        query = query.join(ProductKeywordLink).filter(
            ProductKeywordLink.keyword_id == keyword_id
        )
    products = query.order_by(Product.last_seen_at.desc()).all()

    cards: list[ProductCard] = []
    for product in products:
        snapshot = _latest_snapshot(product)
        relevance = product_relevance(
            product.title,
            category_name=product.category_name,
            shop_name=product.shop_name,
        )
        is_new = False
        if snapshot is not None:
            prior_count = sum(1 for s in product.snapshots if s.id != snapshot.id)
            is_new = prior_count == 0 or snapshot.sales_growth_absolute is None
        else:
            is_new = True

        growth_abs = snapshot.sales_growth_absolute if snapshot else None
        growth_pct = snapshot.sales_growth_percent if snapshot else None
        rank = rank_product(
            relevance_score=relevance.score,
            monthly_sold=snapshot.monthly_sold if snapshot else None,
            sales_growth_absolute=growth_abs,
            sales_growth_percent=growth_pct,
            search_position=snapshot.search_position if snapshot else None,
            shop_score=snapshot.shop_score if snapshot else None,
            good_review_ratio=snapshot.good_review_ratio if snapshot else None,
            is_new=is_new,
        )
        is_fast = rank.label == "tăng nhanh" or (
            growth_pct is not None and growth_pct >= 30
        ) or (growth_abs is not None and growth_abs >= 500)

        if only_relevant and not relevance.accepted:
            continue
        if only_new and not is_new:
            continue
        if only_fast_growth and not is_fast:
            continue
        sold = snapshot.monthly_sold if snapshot else None
        if min_sold is not None and (sold is None or sold < min_sold):
            continue
        price = snapshot.price_cny if snapshot else None
        if min_price is not None and (price is None or price < min_price):
            continue
        if max_price is not None and (price is None or price > max_price):
            continue

        keywords = [
            link.keyword.keyword
            for link in product.keywords
            if link.keyword is not None
        ]
        cards.append(
            ProductCard(
                product=product,
                snapshot=snapshot,
                relevance_score=relevance.score,
                relevance_reasons=relevance.reasons,
                rank_score=rank.score,
                rank_label=rank.label,
                keywords=keywords,
                is_new=is_new,
                is_fast_growth=is_fast,
            )
        )

    if sort == "monthly_sold":
        cards.sort(
            key=lambda c: (c.snapshot.monthly_sold if c.snapshot and c.snapshot.monthly_sold else -1),
            reverse=True,
        )
    elif sort == "growth":
        cards.sort(
            key=lambda c: (
                c.snapshot.sales_growth_absolute
                if c.snapshot and c.snapshot.sales_growth_absolute is not None
                else -10**9
            ),
            reverse=True,
        )
    else:
        cards.sort(key=lambda c: c.rank_score, reverse=True)

    if limit is not None:
        return cards[:limit]
    return cards


def product_to_dict(card: ProductCard) -> dict:
    p = card.product
    s = card.snapshot
    return {
        "id": p.id,
        "external_product_id": p.external_product_id,
        "title": p.title,
        "product_url": p.product_url,
        "main_image_url": p.main_image_url,
        "shop_name": p.shop_name,
        "category_name": p.category_name,
        "first_seen_at": p.first_seen_at.isoformat() if p.first_seen_at else None,
        "last_seen_at": p.last_seen_at.isoformat() if p.last_seen_at else None,
        "price_cny": s.price_cny if s else None,
        "monthly_sold": s.monthly_sold if s else None,
        "sales_growth_absolute": s.sales_growth_absolute if s else None,
        "sales_growth_percent": s.sales_growth_percent if s else None,
        "relevance_score": card.relevance_score,
        "relevance_reasons": card.relevance_reasons,
        "rank_score": card.rank_score,
        "rank_label": card.rank_label,
        "keywords": card.keywords,
        "is_new": card.is_new,
        "is_fast_growth": card.is_fast_growth,
    }
