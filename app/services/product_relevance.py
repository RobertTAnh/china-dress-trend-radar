from __future__ import annotations

from dataclasses import dataclass


INCLUDE_TERMS = {
    "礼服",
    "小礼服",
    "宴会",
    "生日",
    "约会",
    "伴娘",
    "连衣裙",
    "收腰",
    "显瘦",
    "法式",
    "一字肩",
    "斜肩",
    "方领",
    "抹胸",
    "蝴蝶结",
    "花苞",
    "蓬蓬",
    "丝绒",
    "黑色",
    "长裙",
    "中长裙",
}

DRESS_TERMS = {
    "连衣裙",
    "裙子",
    "礼服",
    "小礼服",
    "吊带裙",
    "小黑裙",
    "抹胸裙",
    "蓬蓬裙",
    "长裙",
    "中长裙",
    "伴娘裙",
}

# Bridal wedding dresses only — do NOT exclude 伴娘 (bridesmaid).
EXCLUDE_TERMS = {
    "婚纱",
    "新娘主纱",
    "敬酒服新娘",
    "汉服",
    "古装",
    "儿童",
    "童装",
    "孕妇",
    "睡衣",
    "内衣",
    "泳衣",
    "半身裙",
    "上衣",
    "裤",
    "配饰",
    "鞋",
    "办公",
    "职业装",
    "大码宽松",
    "日常休闲",
}

BRIDAL_ONLY = {
    "婚纱",
    "新娘主纱",
    "主纱",
    "敬酒服新娘",
}


@dataclass
class ProductRelevanceResult:
    score: int
    reasons: list[str]
    accepted: bool


def _contains(text: str, term: str) -> bool:
    return term in text if term else False


def product_relevance(
    title: str,
    *,
    category_name: str = "",
    shop_name: str = "",
) -> ProductRelevanceResult:
    blob = f"{title or ''} {category_name or ''} {shop_name or ''}".strip()
    reasons: list[str] = []
    if not blob:
        return ProductRelevanceResult(0, ["Thiếu tiêu đề"], False)

    # Hard exclusions first.
    for term in sorted(EXCLUDE_TERMS, key=len, reverse=True):
        if term in BRIDAL_ONLY:
            continue
        if _contains(blob, term):
            # Avoid false positives on 伴娘 via 裤 / short garment fragments.
            if term == "裤" and any(d in blob for d in ("连衣裙", "裙子", "礼服", "伴娘裙")):
                continue
            reasons.append(f"Loại vì chứa «{term}»")
            return ProductRelevanceResult(0, reasons, False)

    # "包" by itself is too broad: it also appears in valid dress terms such as
    # 包臀 (bodycon). Only reject explicit bag/accessory phrases.
    if any(term in blob for term in ("女包", "手提包", "单肩包", "斜挎包", "包包")):
        reasons.append("Loại vì là túi/phụ kiện")
        return ProductRelevanceResult(0, reasons, False)

    for term in BRIDAL_ONLY:
        if _contains(blob, term):
            reasons.append(f"Loại váy cưới cô dâu («{term}»)")
            return ProductRelevanceResult(0, reasons, False)
    if "新娘" in blob and "伴娘" not in blob:
        reasons.append("Loại vì liên quan cô dâu (không phải phù dâu)")
        return ProductRelevanceResult(0, reasons, False)

    is_dress = any(_contains(blob, term) for term in DRESS_TERMS)
    if not is_dress:
        reasons.append("Không phải đầm/váy rõ ràng")
        return ProductRelevanceResult(10, reasons, False)

    include_hits = [term for term in INCLUDE_TERMS if _contains(blob, term)]
    score = 40  # base for being a dress
    score += min(40, len(include_hits) * 8)
    if "伴娘" in blob:
        reasons.append("Giữ váy phù dâu (伴娘)")
        score += 5
    if include_hits:
        reasons.append("Khớp Tisora: " + ", ".join(include_hits[:6]))
    else:
        reasons.append("Đầm/váy nhưng ít tín hiệu Tisora")
        score = min(score, 45)

    score = max(0, min(100, score))
    accepted = score >= 50
    if accepted:
        reasons.append("Phù hợp Tisora")
    else:
        reasons.append("Điểm phù hợp thấp")
    return ProductRelevanceResult(score=score, reasons=reasons, accepted=accepted)


def is_relevant_product(title: str, category_name: str = "", shop_name: str = "") -> bool:
    return product_relevance(title, category_name=category_name, shop_name=shop_name).accepted
