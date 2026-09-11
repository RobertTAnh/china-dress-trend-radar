from __future__ import annotations

from collections.abc import Iterable


# Tisora sells youthful, commercially wearable dresses and matching sets. These
# terms intentionally exclude ceremonial/wedding/editorial content that broad
# searches for 礼服 tend to return.
EXCLUDED_TERMS = {
    "明星",
    "红毯",
    "高定",
    "婚纱",
    "新娘",
    "敬酒服",
    "订婚",
    "婚礼",
    "汉服",
    "旗袍",
    "秀场",
    "时装周",
    "颁奖",
    "主持人",
    "舞台",
    "儿童",
    "租赁",
    "礼服馆",
}

PRODUCT_TERMS = {
    "连衣裙",
    "裙子",
    "礼服",
    "女装",
    "吊带裙",
    "小黑裙",
    "抹胸裙",
    "蓬蓬裙",
    "半身裙",
    "长裙",
    "套装",
}

STYLE_TERMS = {
    "轻礼服",
    "小众设计",
    "生日战袍",
    "法式",
    "收腰",
    "显瘦",
    "显高",
    "一字肩",
    "露肩",
    "吊带",
    "抹胸",
    "蝴蝶结",
    "花朵",
    "网纱",
    "泡泡袖",
    "公主风",
    "梨形身材",
    "气质",
}

SHOPPING_TERMS = {"穿搭", "试穿", "上身", "新款", "推荐", "分享", "测评"}


def relevance_text(caption: str | None, hashtags: Iterable[str] | dict | None = None) -> str:
    parts = [caption or ""]
    if isinstance(hashtags, dict):
        parts.extend(str(value) for value in hashtags.values())
    elif hashtags:
        parts.extend(str(value) for value in hashtags)
    return " ".join(parts).lower()


def relevance_score(
    caption: str | None,
    hashtags: Iterable[str] | dict | None = None,
    search_keyword: str | None = None,
) -> int:
    text = relevance_text(caption, hashtags)
    if any(term in text for term in EXCLUDED_TERMS):
        return 0

    score = 0
    product_matches = sum(term in text for term in PRODUCT_TERMS)
    style_matches = sum(term in text for term in STYLE_TERMS)
    shopping_matches = sum(term in text for term in SHOPPING_TERMS)
    score += min(product_matches, 2) * 30
    score += min(style_matches, 4) * 10
    score += min(shopping_matches, 2) * 5
    if search_keyword and search_keyword.lower() in text:
        score += 15
    return min(score, 100)


def is_relevant_video(
    caption: str | None,
    hashtags: Iterable[str] | dict | None = None,
    search_keyword: str | None = None,
    minimum_score: int = 20,
) -> bool:
    return relevance_score(caption, hashtags, search_keyword) >= minimum_score
