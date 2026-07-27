from __future__ import annotations

import asyncio
import collections
import time

from bot.core.config import DANBOORU_MIN_INTERVAL_SEC


class DanbooruRateLimiter:
    """Throttle Danbooru; backs off automatically under burst load."""

    def __init__(self, min_interval: float = DANBOORU_MIN_INTERVAL_SEC) -> None:
        self._lock = asyncio.Lock()
        self._dedup_lock = asyncio.Lock()
        self._last = 0.0
        self._base_interval = min_interval
        self._min_interval = min_interval
        self._inflight: dict[str, asyncio.Future] = {}
        self._window: collections.deque[float] = collections.deque()
        self._window_sec = 60.0
        self._burst_soft = 18
        self._burst_hard = 30
        self._max_interval = 2.5

    def _prune_window(self, now: float) -> None:
        cutoff = now - self._window_sec
        while self._window and self._window[0] < cutoff:
            self._window.popleft()

    def _adapt_interval(self) -> None:
        load = len(self._window)
        if load >= self._burst_hard:
            self._min_interval = self._max_interval
        elif load >= self._burst_soft:
            self._min_interval = min(self._max_interval, self._base_interval * 2.0)
        else:
            self._min_interval = self._base_interval

    def note_rate_limit(self, retry_after: float = 3.0) -> None:
        self._min_interval = min(self._max_interval, max(self._min_interval, retry_after))

    async def acquire(self) -> None:
        async with self._lock:
            now = time.time()
            self._prune_window(now)
            self._adapt_interval()
            wait = self._min_interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.time()
            self._window.append(self._last)

    async def dedup(self, key: str, coro_factory):
        async with self._dedup_lock:
            existing = self._inflight.get(key)
            if existing is not None:
                waiter = existing
                is_owner = False
            else:
                waiter = asyncio.get_running_loop().create_future()
                self._inflight[key] = waiter
                is_owner = True
        if not is_owner:
            return await waiter
        try:
            await self.acquire()
            result = await coro_factory()
            waiter.set_result(result)
            return result
        except Exception as e:
            waiter.set_exception(e)
            raise
        finally:
            async with self._dedup_lock:
                self._inflight.pop(key, None)


DANBOORU_RL = DanbooruRateLimiter()
