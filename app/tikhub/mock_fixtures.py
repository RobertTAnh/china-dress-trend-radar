from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from app.constants import DEFAULT_KEYWORDS
from app.tikhub.normalizer import nested_get


def _aweme(
    video_id: str,
    keyword: str,
    caption: str,
    author: str,
    published_days_ago: int,
    likes: int,
    comments: int,
    shares: int,
    collects: int,
    views: int | None,
    duration_ms: int = 15000,
) -> dict:
    published = datetime.now(timezone.utc) - timedelta(days=published_days_ago)
    stats = {
        "comment_count": comments,
        "digg_count": likes,
        "share_count": shares,
        "collect_count": collects,
    }
    if views is not None:
        stats["play_count"] = views
    cover_hash = hashlib.md5(video_id.encode(), usedforsecurity=False).hexdigest()[:8]
    return {
        "data_id": video_id[-2:],
        "type": 1,
        "data": {
            "type": 1,
            "aweme_info": {
                "aweme_id": video_id,
                "desc": caption,
                "create_time": int(published.timestamp()),
                "share_url": f"https://www.douyin.com/video/{video_id}",
                "author": {
                    "uid": f"u{video_id[-6:]}",
                    "nickname": author,
                },
                "video": {
                    "duration": duration_ms,
                    "cover": {
                        "url_list": [
                            f"https://picsum.photos/seed/{cover_hash}/360/480"
                        ]
                    },
                },
                "cha_list": [{"cha_name": f"#{keyword}"}],
                "statistics": stats,
            },
        },
    }


MOCK_VIDEOS: list[dict] = [
    _aweme("7100000000000000001", "轻熟风连衣裙", "轻熟风连衣裙上身显瘦 #穿搭", "轻礼服衣橱", 1, 8200, 430, 210, 980, 185000),
    _aweme("7100000000000000002", "轻熟风连衣裙", "黑色收腰轻熟风连衣裙试穿", "小个子穿搭", 2, 5400, 190, 88, 640, 92000),
    _aweme("7100000000000000003", "小众连衣裙", "小众连衣裙女新款分享", "设计师衣橱", 4, 12100, 760, 410, 1500, 240000),
    _aweme("7100000000000000004", "小众连衣裙", "短款小众设计连衣裙显高新款试穿", "法式衣橱", 5, 3100, 120, 40, 280, None),
    _aweme("7100000000000000005", "生日约会连衣裙", "红色生日约会连衣裙试穿", "生日穿搭日记", 1, 15600, 980, 620, 2100, 310000),
    _aweme("7100000000000000006", "生日约会连衣裙", "缎面生日约会连衣裙细节", "派对女孩", 6, 2700, 95, 33, 190, 41000),
    _aweme("7100000000000000007", "法式连衣裙", "粉色法式收腰连衣裙女上身", "法式穿搭日记", 0, 9800, 510, 260, 1200, 175000),
    _aweme("7100000000000000008", "法式连衣裙", "法式收腰连衣裙女新款分享", "温柔衣橱", 8, 1600, 70, 21, 110, 22000),
    _aweme("7100000000000000009", "一字肩连衣裙", "一字肩花朵连衣裙气质穿搭", "质感女装", 3, 6400, 240, 95, 720, 88000),
    _aweme("7100000000000000010", "一字肩连衣裙", "立体花朵一字肩连衣裙试穿", "法式衣橱", 12, 4200, 150, 60, 390, None),
    _aweme("7100000000000000011", "抹胸礼服裙试穿", "抹胸蝴蝶结礼服裙试穿露背设计", "ParisLook", 2, 11200, 640, 300, 1400, 205000),
    _aweme("7100000000000000012", "抹胸礼服裙试穿", "抹胸蝴蝶结礼服裙试穿搭配珍珠", "派对造型师", 9, 2300, 80, 28, 160, 36000),
    _aweme("7100000000000000013", "吊带约会礼服裙", "吊带网纱约会礼服裙收腰显瘦", "小个子穿搭", 1, 8700, 390, 170, 860, 142000),
    _aweme("7100000000000000014", "吊带约会礼服裙", "吊带网纱约会礼服裙试穿分享", "裙装工作室", 16, 1900, 55, 18, 90, 27000),
    _aweme("7100000000000000015", "气质小黑裙", "气质小黑裙女收腰显高", "小个子穿搭", 3, 13400, 810, 450, 1700, 268000),
    _aweme("7100000000000000016", "气质小黑裙", "气质小黑裙女鞋跟搭配", "155cm日记", 20, 1100, 40, 12, 70, None),
    _aweme("7100000000000000017", "纯欲辣妹连衣裙", "纯欲辣妹显瘦连衣裙收腰细节", "梨形穿搭", 2, 17800, 1100, 780, 2400, 390000),
    _aweme("7100000000000000018", "纯欲辣妹连衣裙", "纯欲辣妹连衣裙日常也能穿", "质感女装", 11, 3600, 140, 52, 310, 54000),
    _aweme("7100000000000000019", "小个子连衣裙", "小个子显高连衣裙新款试穿", "小个子造型", 4, 7600, 320, 140, 690, 128000),
    _aweme("7100000000000000020", "小个子连衣裙", "小个子显高连衣裙穿搭避坑", "派对穿搭日记", 25, 900, 30, 9, 40, 12000),
    _aweme("7100000000000000021", "轻熟风连衣裙", "丝绒轻熟风连衣裙冬季款", "轻礼服衣橱", 6, 4500, 160, 70, 400, 67000),
    _aweme("7100000000000000022", "小众连衣裙", "绿色小众设计感连衣裙女", "ParisLook", 7, 5100, 200, 90, 470, 79000),
    _aweme("7100000000000000023", "吊带约会礼服裙", "香槟色吊带网纱约会礼服裙更显白", "温柔衣橱", 14, 2800, 100, 35, 210, None),
    _aweme("7100000000000000024", "生日约会连衣裙", "黑色生日约会连衣裙高级感", "生日衣橱", 40, 700, 18, 6, 25, 9000),
]

# Duplicate discovery: same video found by a second keyword.
CROSS_KEYWORD_LINKS = {
    "7100000000000000003": ["小众连衣裙", "轻熟风连衣裙"],
    "7100000000000000005": ["生日约会连衣裙", "轻熟风连衣裙"],
    "7100000000000000015": ["气质小黑裙", "小个子连衣裙"],
    "7100000000000000011": ["抹胸礼服裙试穿", "小众连衣裙"],
}


def _keyword_of(item: dict) -> str:
    return nested_get(item, "data.aweme_info.cha_list")[0]["cha_name"].lstrip("#")


def videos_for_keyword(keyword: str) -> list[dict]:
    matched = []
    for item in MOCK_VIDEOS:
        aweme = item["data"]["aweme_info"]
        vid = aweme["aweme_id"]
        keywords = CROSS_KEYWORD_LINKS.get(vid, [_keyword_of(item)])
        caption = aweme["desc"]
        if keyword in keywords or keyword in caption:
            matched.append(item)
    if not matched:
        matched = MOCK_VIDEOS[:4]
    return matched


def mock_search_page(keyword: str, cursor: int = 0, page_size: int = 8) -> dict:
    items = videos_for_keyword(keyword)
    start = max(int(cursor), 0)
    chunk = items[start : start + page_size]
    next_cursor = start + len(chunk)
    has_more = 1 if next_cursor < len(items) else 0
    return {
        "code": 200,
        "message": "Request successful. This request will incur a charge.",
        "data": {
            "business_data": chunk,
            "cursor": next_cursor,
            "has_more": has_more,
            "search_id": f"mock-search-{keyword}",
            "backtrace": f"bt-{next_cursor}",
        },
    }


def mock_statistics(aweme_ids: list[str]) -> dict:
    stats_list = []
    by_id = {item["data"]["aweme_info"]["aweme_id"]: item for item in MOCK_VIDEOS}
    for aweme_id in aweme_ids:
        item = by_id.get(aweme_id)
        if not item:
            continue
        stats = dict(item["data"]["aweme_info"]["statistics"])
        stats["aweme_id"] = aweme_id
        if "play_count" not in stats:
            stats["play_count"] = 15000
        stats_list.append(stats)
    return {"code": 200, "data": {"statistics_list": stats_list}}


def default_keyword_list() -> list[str]:
    return [word for word, _ in DEFAULT_KEYWORDS]
