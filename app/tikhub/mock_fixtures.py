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
    _aweme("7100000000000000001", "晚礼服", "高级感晚礼服上身效果 #晚礼服", "礼服工作室A", 1, 8200, 430, 210, 980, 185000),
    _aweme("7100000000000000002", "晚礼服", "黑色鱼尾晚礼服适合年会", "小个子穿搭", 2, 5400, 190, 88, 640, 92000),
    _aweme("7100000000000000003", "宴会礼服", "宴会礼服香槟色 recap", "宴会造型师", 4, 12100, 760, 410, 1500, 240000),
    _aweme("7100000000000000004", "宴会礼服", "短款宴会礼服显高", "法式衣橱", 5, 3100, 120, 40, 280, None),
    _aweme("7100000000000000005", "敬酒服", "红色敬酒服出门仪式", "中式嫁衣", 1, 15600, 980, 620, 2100, 310000),
    _aweme("7100000000000000006", "敬酒服", "缎面敬酒服细节", "新娘顾问", 6, 2700, 95, 33, 190, 41000),
    _aweme("7100000000000000007", "生日礼服", "粉色生日礼服蛋糕裙", "派对穿搭日记", 0, 9800, 510, 260, 1200, 175000),
    _aweme("7100000000000000008", "生日礼服", "成人礼生日礼服分享", "18岁衣橱", 8, 1600, 70, 21, 110, 22000),
    _aweme("7100000000000000009", "高级感连衣裙", "高级感连衣裙通勤也能穿", "质感女装", 3, 6400, 240, 95, 720, 88000),
    _aweme("7100000000000000010", "高级感连衣裙", "香风高级感连衣裙", "法式衣橱", 12, 4200, 150, 60, 390, None),
    _aweme("7100000000000000011", "法式礼服", "法式礼服露背设计", "ParisLook", 2, 11200, 640, 300, 1400, 205000),
    _aweme("7100000000000000012", "法式礼服", "法式礼服搭配珍珠", "宴会造型师", 9, 2300, 80, 28, 160, 36000),
    _aweme("7100000000000000013", "显瘦礼服", "显瘦礼服遮肉秘诀", "小个子穿搭", 1, 8700, 390, 170, 860, 142000),
    _aweme("7100000000000000014", "显瘦礼服", "深V显瘦礼服试穿", "礼服工作室A", 16, 1900, 55, 18, 90, 27000),
    _aweme("7100000000000000015", "小个子礼服", "155小个子礼服不显矮", "小个子穿搭", 3, 13400, 810, 450, 1700, 268000),
    _aweme("7100000000000000016", "小个子礼服", "小个子礼服鞋跟搭配", "155cm日记", 20, 1100, 40, 12, 70, None),
    _aweme("7100000000000000017", "新中式礼服", "新中式礼服盘扣细节", "中式嫁衣", 2, 17800, 1100, 780, 2400, 390000),
    _aweme("7100000000000000018", "新中式礼服", "新中式礼服日常也能穿", "质感女装", 11, 3600, 140, 52, 310, 54000),
    _aweme("7100000000000000019", "年会礼服", "年会礼服闪光面料", "年会造型", 4, 7600, 320, 140, 690, 128000),
    _aweme("7100000000000000020", "年会礼服", "年会礼服出租避坑", "派对穿搭日记", 25, 900, 30, 9, 40, 12000),
    _aweme("7100000000000000021", "晚礼服", "丝绒晚礼服冬季款", "礼服工作室A", 6, 4500, 160, 70, 400, 67000),
    _aweme("7100000000000000022", "宴会礼服", "绿色宴会礼服小众色", "ParisLook", 7, 5100, 200, 90, 470, 79000),
    _aweme("7100000000000000023", "敬酒服", "香槟色敬酒服更显白", "新娘顾问", 14, 2800, 100, 35, 210, None),
    _aweme("7100000000000000024", "生日礼服", "黑色生日礼服高级感", "18岁衣橱", 40, 700, 18, 6, 25, 9000),
]

# Duplicate discovery: same video found by a second keyword.
CROSS_KEYWORD_LINKS = {
    "7100000000000000003": ["宴会礼服", "年会礼服"],
    "7100000000000000005": ["敬酒服", "新中式礼服"],
    "7100000000000000015": ["小个子礼服", "显瘦礼服"],
    "7100000000000000011": ["法式礼服", "晚礼服"],
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
