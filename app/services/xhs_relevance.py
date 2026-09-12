from __future__ import annotations

from dataclasses import dataclass, field


INCLUDE_TERMS = {
    "连衣裙",
    "小礼服",
    "生日穿搭",
    "宴会穿搭",
    "派对穿搭",
    "一字肩",
    "斜肩",
    "抹胸",
    "吊带",
    "收腰",
    "蝴蝶结",
    "花朵",
    "蕾丝",
    "公主裙",
    "千金风",
    "纯欲风",
    "法式",
    "赫本风",
    "辣妹裙",
}

FASHION_SIGNAL_TERMS = {
    "连衣裙",
    "裙子",
    "礼服",
    "小礼服",
    "吊带裙",
    "抹胸裙",
    "公主裙",
    "辣妹裙",
    "穿搭",
    "女装",
    "伴娘裙",
}

EXCLUDE_TERMS = {
    "女童",
    "儿童",
    "童装",
    "宝宝",
    "周岁",
    "花童",
    "婚纱",
    "明星活动",
    "红毯",
    "娱乐",
    "颁奖",
    "高定秀场",
    "新闻",
    "男装",
    "汉服",
    "睡衣",
    "毛衣裙",
    "妈妈装",
    "中老年",
}

BRIDAL_ONLY = {
    "婚纱",
    "新娘主纱",
    "主纱",
}


@dataclass
class XhsRelevanceResult:
    accepted: bool
    score: int
    matched_positive_terms: list[str] = field(default_factory=list)
    matched_negative_terms: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def xhs_relevance(
    title: str = "",
    description: str = "",
    author_name: str = "",
    *,
    hashtags: str = "",
) -> XhsRelevanceResult:
    blob = f"{title or ''} {description or ''} {hashtags or ''} {author_name or ''}".strip()
    if not blob:
        return XhsRelevanceResult(
            accepted=False,
            score=0,
            rejection_reasons=["Thiếu tiêu đề và mô tả"],
            reasons=["Thiếu tiêu đề và mô tả"],
        )

    negative = [term for term in sorted(EXCLUDE_TERMS, key=len, reverse=True) if term in blob]
    if "新娘" in blob and "伴娘" not in blob:
        negative.append("新娘")
    for term in BRIDAL_ONLY:
        if term in blob and term not in negative:
            negative.append(term)

    if negative:
        reasons = [f"Loại vì chứa «{term}»" for term in negative[:6]]
        if "新娘" in negative and "伴娘" not in blob:
            reasons = ["Loại váy cưới / cô dâu (không phải phù dâu)"] + reasons
        return XhsRelevanceResult(
            accepted=False,
            score=0,
            matched_negative_terms=negative,
            rejection_reasons=reasons,
            reasons=reasons,
        )

    fashion_hits = [term for term in FASHION_SIGNAL_TERMS if term in blob]
    if not fashion_hits:
        reason = "Không có tín hiệu thời trang/đầm rõ ràng trong nội dung"
        return XhsRelevanceResult(
            accepted=False,
            score=15,
            rejection_reasons=[reason],
            reasons=[reason],
        )

    positive = [term for term in INCLUDE_TERMS if term in blob]
    score = 40
    score += min(40, len(positive) * 8)
    reasons: list[str] = []
    if "伴娘" in blob:
        reasons.append("Giữ váy phù dâu (伴娘)")
        score += 5
    if positive:
        reasons.append("Khớp Tisora: " + ", ".join(positive[:6]))
    else:
        reasons.append("Có tín hiệu đầm/váy nhưng ít từ khóa Tisora")
        score = min(score, 48)

    score = max(0, min(100, score))
    accepted = score >= 50
    if accepted:
        reasons.append("Phù hợp Tisora")
    else:
        reasons.append("Điểm phù hợp thấp")
    return XhsRelevanceResult(
        accepted=accepted,
        score=score,
        matched_positive_terms=positive,
        matched_negative_terms=[],
        rejection_reasons=[] if accepted else reasons,
        reasons=reasons,
    )
