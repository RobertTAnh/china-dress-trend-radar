from __future__ import annotations

from collections.abc import Iterable


# Tisora sells youthful, commercially wearable dresses and matching sets. These
# terms intentionally exclude ceremonial/wedding/editorial content that broad
# searches for 礼服 tend to return.
EXCLUDED_TERMS = {
    "明星",
    "演员",
    "艺人",
    "追星",
    "娱乐",
    "盛典",
    "追剧",
    "品牌活动",
    "选美",
    "世界小姐",
    "亮相",
    "歌会",
    "红毯",
    "高定",
    "婚纱",
    "新娘",
    "敬酒服",
    "主纱",
    "婚服",
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
    "车展",
    "车模",
    "半身裙",
}

EXCLUDED_AUTHOR_TERMS = {
    "娱乐",
    "追星",
    "娱记",
    "明星",
    "影视",
    "剧综",
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
    "伴娘",
}

SHOPPING_TERMS = {
    "穿搭",
    "试穿",
    "上身",
    "新款",
    "推荐",
    "分享",
    "测评",
    "商品",
    "版型",
    "面料",
    "显瘦",
}

OCCASION_TERMS = {
    "生日",
    "约会",
    "聚餐",
    "派对",
    "轻礼服",
    "伴娘",
    "婚礼",
    "结婚",
    "订婚",
}


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
    author_name: str | None = None,
) -> int:
    text = relevance_text(caption, hashtags)
    author = (author_name or "").lower()
    if any(term in text for term in EXCLUDED_TERMS) or any(
        term in author for term in EXCLUDED_AUTHOR_TERMS
    ):
        return 0

    score = 0
    product_matches = sum(term in text for term in PRODUCT_TERMS)
    style_matches = sum(term in text for term in STYLE_TERMS)
    shopping_matches = sum(term in text for term in SHOPPING_TERMS)
    occasion_matches = sum(term in text for term in OCCASION_TERMS)
    score += min(product_matches, 2) * 30
    score += min(style_matches, 4) * 10
    score += min(shopping_matches, 2) * 5
    score += min(occasion_matches, 2) * 10
    if search_keyword and search_keyword.lower() in text:
        score += 15
    return max(min(score, 100), 0)


def is_relevant_video(
    caption: str | None,
    hashtags: Iterable[str] | dict | None = None,
    search_keyword: str | None = None,
    author_name: str | None = None,
    minimum_score: int = 60,
) -> bool:
    return relevance_score(caption, hashtags, search_keyword, author_name) >= minimum_score
