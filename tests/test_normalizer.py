from datetime import datetime, timezone

from app.tikhub.normalizer import normalize_search_response, normalize_video
from tests.conftest import sample_aweme, sample_search_payload


def test_normalize_core_fields():
    video = normalize_video(sample_aweme("999", views=3210, likes=44))
    assert video is not None
    assert video.external_video_id == "999"
    assert video.caption == "晚礼服试穿 #晚礼服"
    assert video.author_id == "u1"
    assert video.author_name == "Shop A"
    assert video.metrics.like_count == 44
    assert video.metrics.view_count == 3210
    assert video.source_url.endswith("/999")
    assert video.cover_url.startswith("https://")
    assert "晚礼服" in video.hashtags
    assert video.published_at == datetime.fromtimestamp(1710000000, tz=timezone.utc).replace(tzinfo=None)
    assert video.raw_data["aweme_id"] == "999"


def test_missing_views_stay_null():
    video = normalize_video(sample_aweme("1", views=None))
    assert video is not None
    assert video.metrics.view_count is None
    assert video.metrics.like_count == 100


def test_alternate_field_names():
    aweme = {
        "awemeId": "888",
        "description": "hello",
        "createTime": 1710000000,
        "shareUrl": "https://www.douyin.com/video/888",
        "author_info": {"id": "x", "nick_name": "N"},
        "stats": {"likeCount": 9, "commentCount": 2, "shareCount": 1, "collectCount": 3},
    }
    video = normalize_video(aweme)
    assert video.external_video_id == "888"
    assert video.caption == "hello"
    assert video.metrics.like_count == 9
    assert video.metrics.view_count is None


def test_zero_views_are_kept():
    video = normalize_video(sample_aweme("2", views=0))
    assert video.metrics.view_count == 0


def test_search_payload_nested_business_data():
    payload = sample_search_payload([sample_aweme("11"), sample_aweme("12")], cursor=16, has_more=1)
    page = normalize_search_response(payload)
    assert [item.external_video_id for item in page.videos] == ["11", "12"]
    assert page.cursor == 16
    assert page.has_more is True
    assert page.search_id == "sid"
    assert page.backtrace == "bt"


def test_general_search_list_shape():
    payload = {
        "data": [
            {"type": 1, "aweme_info": sample_aweme("21")},
            {"type": 1, "aweme_info": sample_aweme("22")},
        ],
        "cursor": 20,
        "has_more": 0,
        "search_id": "g1",
        "backtrace": "b1",
    }
    page = normalize_search_response(payload)
    assert len(page.videos) == 2
    assert page.has_more is False
    assert page.search_id == "g1"
