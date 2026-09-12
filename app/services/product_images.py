from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

IMAGE_DIR = DATA_DIR / "product-images"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_HOST_SUFFIXES = (".ecombdimg.com", ".byteimg.com", ".douyinvod.com")
CONTENT_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _safe_source_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(
        host == suffix[1:] or host.endswith(suffix) for suffix in ALLOWED_HOST_SUFFIXES
    )


def cached_image_path(external_product_id: str) -> Path | None:
    safe_id = "".join(ch for ch in external_product_id if ch.isalnum() or ch in "-_")
    if not safe_id:
        return None
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    matches = sorted(IMAGE_DIR.glob(f"{safe_id}.*"))
    return matches[0] if matches else None


async def cache_product_image(external_product_id: str, source_url: str) -> Path | None:
    existing = cached_image_path(external_product_id)
    if existing is not None:
        return existing
    if not _safe_source_url(source_url):
        logger.warning("Skip unsafe product image host id=%s", external_product_id)
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Referer": "https://www.douyin.com/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(source_url, headers=headers)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        extension = CONTENT_EXTENSIONS.get(content_type)
        if extension is None or not response.content or len(response.content) > MAX_IMAGE_BYTES:
            logger.warning(
                "Invalid product image id=%s type=%s bytes=%s",
                external_product_id,
                content_type,
                len(response.content),
            )
            return None
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        destination = IMAGE_DIR / f"{external_product_id}{extension}"
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(response.content)
        temporary.replace(destination)
        logger.info(
            "Product image cached id=%s file=%s bytes=%s",
            external_product_id,
            destination.name,
            len(response.content),
        )
        return destination
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Product image cache failed id=%s reason=%s", external_product_id, exc)
        return None


async def cache_product_images(items: list[tuple[str, str]], concurrency: int = 4) -> None:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(product_id: str, url: str) -> None:
        async with semaphore:
            await cache_product_image(product_id, url)

    await asyncio.gather(*(one(product_id, url) for product_id, url in items))
