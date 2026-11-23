"""Thread-safe per-key sliding-window rate limiting."""

import math
import os
import threading
import time
from collections import defaultdict, deque

from api.errors import APIError


class SlidingWindowRateLimiter:
    """Keep request timestamps in a bounded window for each API key."""

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: float | None = None,
    ) -> None:
        self.max_requests = (
            int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "60"))
            if max_requests is None
            else max_requests
        )
        self.window_seconds = (
            float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
            if window_seconds is None
            else window_seconds
        )
        if self.max_requests <= 0 or self.window_seconds <= 0:
            raise ValueError("Rate-limit values must be greater than zero")
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Record one request, raising a structured 429 if the limit is reached."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.max_requests:
                retry_after = max(
                    1,
                    math.ceil(self.window_seconds - (now - timestamps[0])),
                )
                raise APIError(
                    status_code=429,
                    code="RATE_LIMIT_EXCEEDED",
                    message="Too many requests. Please retry after the indicated delay.",
                    headers={"Retry-After": str(retry_after)},
                )
            timestamps.append(now)
