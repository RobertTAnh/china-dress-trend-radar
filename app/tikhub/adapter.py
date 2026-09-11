from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.logging_utils import redact_secrets
from app.tikhub.mock_fixtures import mock_search_page, mock_statistics
from app.tikhub.normalizer import (
    SearchPage,
    merge_statistics,
    normalize_search_response,
)
from app.tikhub.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


class TikHubAuthError(Exception):
    pass


class TikHubClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TikHubBudgetSignal(Exception):
    pass


class TikHubAdapter:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
        mock_mode: bool | None = None,
        rate_limiter: AsyncRateLimiter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.mock_mode = self.settings.mock_mode if mock_mode is None else mock_mode
        self._client = client
        self._owns_client = client is None
        self.rate_limiter = rate_limiter or AsyncRateLimiter(
            self.settings.internal_rate_limit_rps
        )

    @property
    def search_path(self) -> str:
        if self.settings.tikhub_use_fallback_search:
            return self.settings.tikhub_search_fallback_endpoint
        return self.settings.tikhub_search_endpoint

    def _headers(self) -> dict[str, str]:
        key = (self.settings.tikhub_api_key or "").strip()
        if not key and not self.mock_mode:
            raise TikHubAuthError("Thiếu TIKHUB_API_KEY. Hãy đặt trong .env hoặc bật MOCK_MODE.")
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    async def _client_obj(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.tikhub_base_url.rstrip("/"),
                timeout=self.settings.http_timeout_seconds,
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search_videos(
        self,
        keyword: str,
        cursor: int = 0,
        search_id: str = "",
        backtrace: str = "",
        sort_type: str | None = None,
        publish_time: str | None = None,
        content_type: str | None = None,
    ) -> SearchPage:
        if self.mock_mode:
            payload = mock_search_page(keyword, cursor=cursor)
            return normalize_search_response(payload)

        body = {
            "keyword": keyword,
            "cursor": cursor,
            "sort_type": sort_type or self.settings.search_sort_type,
            "publish_time": publish_time or self.settings.search_publish_time,
            "filter_duration": "0",
            "content_type": content_type or self.settings.search_content_type,
            "search_id": search_id or "",
            "backtrace": backtrace or "",
        }
        payload = await self._request("POST", self.search_path, json=body)
        return normalize_search_response(payload)

    async def fetch_statistics(self, aweme_ids: list[str]) -> dict[str, Any]:
        ids = [item for item in aweme_ids if item][:2]
        if not ids:
            return {"code": 200, "data": {}}
        if self.mock_mode:
            return mock_statistics(ids)
        try:
            return await self._fetch_statistics_once(ids)
        except TikHubClientError as exc:
            if len(ids) == 1:
                raise
            # One bad id in a pair can make TikHub return 400 for the whole batch.
            logger.warning(
                "Batch statistics failed (%s); retrying one-by-one",
                exc.status_code,
            )
            merged: dict[str, Any] = {"code": 200, "data": {"statistics_list": []}}
            for aweme_id in ids:
                try:
                    payload = await self._fetch_statistics_once([aweme_id])
                except TikHubClientError as single_exc:
                    logger.warning(
                        "Skip statistics for aweme_id=%s status=%s",
                        aweme_id,
                        single_exc.status_code,
                    )
                    continue
                items = []
                data = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(data, dict) and isinstance(data.get("statistics_list"), list):
                    items = data["statistics_list"]
                elif isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = [data]
                merged["data"]["statistics_list"].extend(
                    item for item in items if isinstance(item, dict)
                )
            return merged

    async def _fetch_statistics_once(self, ids: list[str]) -> dict[str, Any]:
        # Keep comma unescaped; some TikHub gateways reject %2C.
        query = ",".join(ids)
        path = f"{self.settings.tikhub_stats_endpoint}?aweme_ids={query}"
        return await self._request("GET", path)

    async def enrich_views(self, page_or_videos, aweme_ids: list[str]) -> None:
        if not aweme_ids:
            return
        payload = await self.fetch_statistics(aweme_ids)
        videos = page_or_videos.videos if isinstance(page_or_videos, SearchPage) else page_or_videos
        by_id = {video.external_video_id: video for video in videos}
        for aweme_id in aweme_ids:
            video = by_id.get(aweme_id)
            if video:
                merge_statistics(video, payload)

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = await self._client_obj()
        attempts = self.settings.retry_max_attempts
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            await self.rate_limiter.acquire()
            try:
                response = await client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers=self._headers(),
                )
            except httpx.RequestError as exc:
                last_error = exc
                logger.warning(
                    "TikHub network error on %s %s (attempt %s/%s): %s",
                    method,
                    path,
                    attempt,
                    attempts,
                    redact_secrets(str(exc)),
                )
                if attempt >= attempts:
                    break
                await asyncio.sleep(self._backoff(attempt))
                continue

            if response.status_code in (401, 403):
                logger.error("TikHub authentication failed for %s %s", method, path)
                raise TikHubAuthError("TikHub từ chối xác thực. Kiểm tra TIKHUB_API_KEY.")

            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "TikHub retryable status %s on %s %s (attempt %s/%s)",
                    response.status_code,
                    method,
                    path,
                    attempt,
                    attempts,
                )
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
                if attempt >= attempts:
                    break
                await asyncio.sleep(self._backoff(attempt))
                continue

            if response.status_code >= 400:
                body = ""
                try:
                    body = response.text[:500]
                except Exception:
                    body = ""
                logger.error(
                    "TikHub client error %s on %s %s body=%s",
                    response.status_code,
                    method,
                    path.split("?", 1)[0],
                    redact_secrets(body),
                )
                raise TikHubClientError(
                    f"TikHub HTTP {response.status_code}",
                    status_code=response.status_code,
                    body=redact_secrets(body),
                )

            try:
                return response.json()
            except ValueError as exc:
                last_error = exc
                logger.error("TikHub returned non-JSON for %s %s", method, path)
                break

        assert last_error is not None
        raise last_error

    def _backoff(self, attempt: int) -> float:
        return self.settings.retry_base_delay_seconds * (2 ** (attempt - 1))
