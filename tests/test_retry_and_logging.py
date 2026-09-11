import logging

import httpx
import pytest
import respx

from app.config import get_settings
from app.logging_utils import RedactFilter, redact_secrets
from app.tikhub.adapter import TikHubAdapter, TikHubAuthError
from tests.conftest import sample_aweme, sample_search_payload

SEARCH_URL = "https://api.tikhub.io/api/v1/douyin/search/fetch_video_search_v2"


def _adapter(client: httpx.AsyncClient) -> TikHubAdapter:
    settings = get_settings().model_copy(
        update={
            "tikhub_api_key": "super-secret-token-xyz",
            "mock_mode": False,
            "retry_base_delay_seconds": 0.01,
            "retry_max_attempts": 3,
            "internal_rate_limit_rps": 100,
        }
    )
    return TikHubAdapter(settings=settings, client=client, mock_mode=False)


@pytest.mark.asyncio
@respx.mock
async def test_retry_on_429_then_success():
    payload = sample_search_payload([sample_aweme("55")], has_more=0)
    route = respx.post(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json=payload),
        ]
    )
    async with httpx.AsyncClient(base_url="https://api.tikhub.io") as client:
        adapter = _adapter(client)
        page = await adapter.search_videos("晚礼服")
    assert route.call_count == 3
    assert page.videos[0].external_video_id == "55"


@pytest.mark.asyncio
@respx.mock
async def test_no_retry_on_401():
    route = respx.post(SEARCH_URL).mock(return_value=httpx.Response(401, json={"message": "nope"}))
    async with httpx.AsyncClient(base_url="https://api.tikhub.io") as client:
        adapter = _adapter(client)
        with pytest.raises(TikHubAuthError):
            await adapter.search_videos("晚礼服")
    assert route.call_count == 1


def test_redact_api_key_from_logs(caplog):
    logger = logging.getLogger("test_redact")
    logger.addFilter(RedactFilter())
    logger.setLevel(logging.INFO)
    with caplog.at_level(logging.INFO, logger="test_redact"):
        logger.info("Authorization: Bearer super-secret-token-xyz")
        logger.info("TIKHUB_API_KEY=super-secret-token-xyz")
    text = " ".join(record.getMessage() for record in caplog.records)
    assert "super-secret-token-xyz" not in text
    assert "[REDACTED]" in text
    assert "super-secret-token-xyz" not in redact_secrets("Bearer super-secret-token-xyz")


@pytest.mark.asyncio
async def test_statistics_retries_400_then_splits_into_chunks():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("aweme_ids", "")
        calls.append(query)
        ids = query.split(",") if query else []
        if len(ids) > 10:
            return httpx.Response(400, json={"message": "retry"})
        return httpx.Response(
            200,
            json={
                "data": {
                    "statistics_list": [
                        {"aweme_id": item, "play_count": 100} for item in ids
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://api.tikhub.io", transport=transport
    ) as client:
        adapter = _adapter(client)
        payload = await adapter.fetch_statistics([str(index) for index in range(23)])

    assert len(calls) == 6  # Three full attempts, followed by 10 + 10 + 3.
    assert adapter.last_statistics_request_count == 3
    assert len(payload["_chunk_payloads"]) == 3
