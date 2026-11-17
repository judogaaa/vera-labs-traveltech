"""Bounded, process-local abuse limits for the trip planner demo.

The API is a single-host demo, so an in-process sliding window plus a
bounded concurrency gate is enough to keep one client from exhausting the
LLM/geo/PDF workers.  A multi-host deployment must replace this with a
shared limiter (Redis or the reverse proxy) - see SECURITY.md.
"""

from __future__ import annotations

import threading
import time
from collections import deque

_MAX_KEYS = 4096


class SlidingWindowLimiter:
    def __init__(self, max_keys: int = _MAX_KEYS) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = {}
        self._max_keys = max_keys

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._events.get(key)
            if bucket is not None:
                while bucket and now - bucket[0] >= window_seconds:
                    bucket.popleft()
            if bucket is None or not bucket:
                if key not in self._events and len(self._events) >= self._max_keys:
                    # Drop the oldest key; authenticated data is unaffected.
                    self._events.pop(next(iter(self._events)), None)
                bucket = deque()
                self._events[key] = bucket
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


class ConcurrencyGate:
    """Non-blocking bounded semaphore with a very short wait."""

    def __init__(self, slots: int) -> None:
        self._sem = threading.BoundedSemaphore(max(1, slots))

    def acquire(self, timeout: float = 0.25) -> bool:
        return self._sem.acquire(timeout=timeout)

    def release(self) -> None:
        try:
            self._sem.release()
        except ValueError:  # pragma: no cover - double release guard
            pass
