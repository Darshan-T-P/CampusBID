"""In-memory sliding-window rate limiting (fine for a single-process server).

Counts attempts per key inside a time window and reports how long to wait once the limit
is hit. It slows down password guessing, code guessing and signup spam.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from app.core.config import settings


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def retry_after(self, key: str, limit: int, window: float) -> int | None:
        """Record an attempt. Returns seconds to wait if over the limit, else None."""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= window:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, int(window - (now - hits[0])) + 1)
        hits.append(now)
        return None

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


def enforce(key: str, limit: int, window: float) -> None:
    """Raise 429 (with Retry-After) if `key` exceeded `limit` attempts in `window` seconds."""
    if not settings.rate_limit_enabled:
        return
    wait = limiter.retry_after(key, limit, window)
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(wait)},
        )
