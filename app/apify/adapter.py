from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.apify.mock_fixtures import (
    mock_actor_run_finished,
    mock_actor_run_start,
    mock_dataset_items,
)
from app.apify.normalizer import NormalizedProduct, normalize_dataset_items
from app.config import Settings, get_settings
from app.logging_utils import redact_secrets

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {
    "SUCCEEDED",
    "FAILED",
    "TIMED-OUT",
    "TIMED_OUT",
    "ABORTED",
    "ABORTING",
}


class ApifyAuthError(Exception):
    pass


class ApifyUpstreamError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ApifyTimeoutError(Exception):
    pass


class ApifyBudgetError(Exception):
    pass


@dataclass
class ApifyRunResult:
    run_id: str
    dataset_id: str
    status: str
    items: list[NormalizedProduct]
    raw_items: list[dict[str, Any]]


class ApifyAdapter:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
        mock_mode: bool | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.mock_mode = (
            self.settings.product_mock_mode if mock_mode is None else mock_mode
        )
        self._client = client
        self._owns_client = client is None
        self.last_run_id: str | None = None
        self.last_dataset_id: str | None = None

    def actor_path_id(self) -> str:
        actor_id = (self.settings.apify_actor_id or "").strip()
        return actor_id.replace("/", "~")

    def _headers(self) -> dict[str, str]:
        token = (self.settings.apify_token or "").strip()
        if not token and not self.mock_mode:
            raise ApifyAuthError("Thiếu APIFY_TOKEN. Hãy đặt trong .env hoặc bật PRODUCT_MOCK_MODE.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _client_obj(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.apify_base_url.rstrip("/"),
                timeout=self.settings.http_timeout_seconds,
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search_products(
        self,
        keyword: str,
        *,
        max_results: int = 20,
        include_details: bool = False,
    ) -> ApifyRunResult:
        keyword = keyword.strip()
        if not keyword:
            raise ApifyUpstreamError("Từ khóa sản phẩm trống.")
        if self.mock_mode:
            return await self._mock_search(keyword, max_results=max_results)

        run_payload = await self.start_run(
            keyword,
            max_results=max_results,
            include_details=include_details,
        )
        run_data = run_payload.get("data") or {}
        run_id = str(run_data.get("id") or "")
        dataset_id = str(run_data.get("defaultDatasetId") or "")
        if not run_id:
            raise ApifyUpstreamError("Apify không trả run id.")
        self.last_run_id = run_id
        self.last_dataset_id = dataset_id or None

        finished = await self.wait_for_run(run_id)
        status = str((finished.get("data") or {}).get("status") or "")
        dataset_id = str(
            (finished.get("data") or {}).get("defaultDatasetId") or dataset_id or ""
        )
        self.last_dataset_id = dataset_id or None
        if status.upper() not in {"SUCCEEDED", "SUCCEEDED".upper()}:
            if status.upper() in {"TIMED-OUT", "TIMED_OUT"}:
                raise ApifyTimeoutError(f"Apify run timeout: {run_id}")
            raise ApifyUpstreamError(f"Apify run kết thúc với trạng thái {status or 'unknown'}")
        if not dataset_id:
            raise ApifyUpstreamError("Apify run thiếu defaultDatasetId.")

        raw_items = await self.fetch_dataset_items(dataset_id)
        products = normalize_dataset_items(raw_items, keyword=keyword)[:max_results]
        return ApifyRunResult(
            run_id=run_id,
            dataset_id=dataset_id,
            status=status,
            items=products,
            raw_items=raw_items,
        )

    async def start_run(
        self,
        keyword: str,
        *,
        max_results: int = 20,
        include_details: bool = False,
    ) -> dict[str, Any]:
        actor_id = quote(self.actor_path_id(), safe="~")
        body = {
            "keywords": [keyword],
            "maxResults": max_results,
            "includeDetails": include_details,
        }
        path = f"/v2/acts/{actor_id}/runs"
        return await self._request("POST", path, json=body)

    async def wait_for_run(self, run_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + float(self.settings.apify_run_timeout_seconds)
        last_payload: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            wait_seconds = min(60, max(1, int(self.settings.apify_poll_interval_seconds)))
            path = f"/v2/actor-runs/{quote(run_id, safe='')}"
            payload = await self._request(
                "GET",
                path,
                params={"waitForFinish": wait_seconds},
            )
            last_payload = payload
            status = str(((payload.get("data") or {}).get("status") or "")).upper()
            if status in TERMINAL_STATUSES or status == "SUCCEEDED":
                return payload
            await asyncio.sleep(self.settings.apify_poll_interval_seconds)
        raise ApifyTimeoutError(
            f"Hết thời gian chờ Apify run {run_id}. "
            f"payload={redact_secrets(str(last_payload)[:300]) if last_payload else 'none'}"
        )

    async def fetch_dataset_items(self, dataset_id: str) -> list[dict[str, Any]]:
        path = f"/v2/datasets/{quote(dataset_id, safe='')}/items"
        payload = await self._request(
            "GET",
            path,
            params={"format": "json", "clean": 1},
        )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            items = payload.get("data") or payload.get("items") or []
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    async def _mock_search(self, keyword: str, *, max_results: int) -> ApifyRunResult:
        start = mock_actor_run_start(keyword)
        run_id = str(start["data"]["id"])
        dataset_id = str(start["data"]["defaultDatasetId"])
        self.last_run_id = run_id
        self.last_dataset_id = dataset_id
        finished = mock_actor_run_finished(run_id, dataset_id)
        raw_items = mock_dataset_items(keyword)[:max_results]
        products = normalize_dataset_items(raw_items, keyword=keyword)
        return ApifyRunResult(
            run_id=run_id,
            dataset_id=dataset_id,
            status=str(finished["data"]["status"]),
            items=products,
            raw_items=raw_items,
        )

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        client = await self._client_obj()
        attempts = self.settings.retry_max_attempts
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
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
                    "Apify network error on %s %s (attempt %s/%s): %s",
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
                logger.error("Apify authentication failed for %s %s", method, path)
                raise ApifyAuthError("Apify từ chối xác thực. Kiểm tra APIFY_TOKEN.")

            body_preview = ""
            try:
                body_preview = redact_secrets(response.text[:500])
            except Exception:
                body_preview = ""

            lowered = body_preview.lower()
            if response.status_code in (402, 402) or any(
                token in lowered
                for token in ("insufficient credit", "out of credit", "payment required", "quota")
            ):
                raise ApifyBudgetError(
                    f"Apify báo hết credit/quota (HTTP {response.status_code})."
                )

            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "Apify retryable status %s on %s %s (attempt %s/%s)",
                    response.status_code,
                    method,
                    path,
                    attempt,
                    attempts,
                )
                last_error = ApifyUpstreamError(
                    f"Apify HTTP {response.status_code}",
                    status_code=response.status_code,
                    body=body_preview,
                )
                if attempt >= attempts:
                    break
                await asyncio.sleep(self._backoff(attempt))
                continue

            if response.status_code >= 400:
                logger.error(
                    "Apify client error %s on %s %s body=%s",
                    response.status_code,
                    method,
                    path,
                    body_preview,
                )
                raise ApifyUpstreamError(
                    f"Apify HTTP {response.status_code}",
                    status_code=response.status_code,
                    body=body_preview,
                )

            # Dataset items endpoint may return a bare JSON array.
            content_type = response.headers.get("content-type", "")
            try:
                return response.json()
            except ValueError as exc:
                last_error = exc
                logger.error(
                    "Apify returned non-JSON for %s %s content_type=%s",
                    method,
                    path,
                    content_type,
                )
                break

        assert last_error is not None
        if isinstance(last_error, ApifyUpstreamError):
            raise last_error
        raise ApifyUpstreamError(redact_secrets(str(last_error)))

    def _backoff(self, attempt: int) -> float:
        return self.settings.retry_base_delay_seconds * (2 ** (attempt - 1))
