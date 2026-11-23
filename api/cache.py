"""Thread-safe TTL cache for stateless API responses."""

import copy
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Optional


class TTLCache:
    """Cache values by key until their time-to-live expires."""

    def __init__(
        self,
        ttl_seconds: Optional[float] = None,
        max_entries: int = 1024,
    ) -> None:
        self.ttl_seconds = (
            float(os.getenv("CACHE_TTL_SECONDS", "60"))
            if ttl_seconds is None
            else ttl_seconds
        )
        if self.ttl_seconds <= 0 or max_entries <= 0:
            raise ValueError("Cache TTL and max_entries must be greater than zero")
        self.max_entries = max_entries
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[bool, Any]:
        """Return a deep-copied cached value and whether it was still valid."""
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False, None
            expires_at, value = entry
            if expires_at <= now:
                del self._entries[key]
                return False, None
            self._entries.move_to_end(key)
            return True, copy.deepcopy(value)

    def set(self, key: str, value: Any) -> None:
        """Store a value with a fresh TTL, evicting least-recently-used entries."""
        with self._lock:
            self._entries[key] = (
                time.monotonic() + self.ttl_seconds,
                copy.deepcopy(value),
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
