from __future__ import annotations

import asyncio
import time


class AsyncRateLimiter:
    def __init__(self, requests_per_second: float = 2.0) -> None:
        self.min_interval = 1.0 / max(requests_per_second, 0.1)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
