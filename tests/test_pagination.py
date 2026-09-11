from app.tikhub.normalizer import extract_pagination, normalize_search_response
from tests.conftest import sample_aweme


def test_pagination_fields_from_page():
    payload = {
        "data": {
            "business_data": [{"data": {"aweme_info": sample_aweme("1")}}],
            "cursor": 12,
            "search_id": "abc",
            "backtrace": "zz",
            "has_more": 1,
        }
    }
    page = normalize_search_response(payload)
    assert page.cursor == 12
    assert page.search_id == "abc"
    assert page.backtrace == "zz"
    assert page.has_more is True


def test_pagination_has_more_zero():
    cursor, search_id, backtrace, has_more = extract_pagination(
        {"data": {"cursor": 0, "search_id": "", "backtrace": "", "has_more": 0}}
    )
    assert cursor == 0
    assert has_more is False
    assert search_id == ""
    assert backtrace == ""


def test_second_page_uses_previous_cursor():
    first = normalize_search_response(
        {
            "data": {
                "business_data": [{"data": {"aweme_info": sample_aweme("1")}}],
                "cursor": 8,
                "search_id": "keep-me",
                "backtrace": "bt-8",
                "has_more": 1,
            }
        }
    )
    second = normalize_search_response(
        {
            "data": {
                "business_data": [{"data": {"aweme_info": sample_aweme("2")}}],
                "cursor": 16,
                "search_id": first.search_id,
                "backtrace": first.backtrace,
                "has_more": 0,
            }
        }
    )
    assert first.cursor == 8
    assert second.search_id == "keep-me"
    assert second.has_more is False
