"""Rate limiting — per-key and global, sliding window."""

from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Literal


def _parse_rate(rate_str: str) -> tuple[int, int]:
    """Parse a rate string like '100/minute' into (count, seconds).

    Supported units: second, minute, hour, day.
    """
    pattern = r"^(\d+)/(second|minute|hour|day)s?$"
    m = re.match(pattern, rate_str.strip().lower())
    if not m:
        raise ValueError(
            f"Invalid rate string: {rate_str!r}. "
            "Expected format: '<count>/<unit>' e.g. '100/minute'"
        )
    count = int(m.group(1))
    unit = m.group(2)
    unit_seconds = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    return count, unit_seconds[unit]


@dataclass
class _Window:
    """Sliding window request tracker for one key."""
    timestamps: deque = field(default_factory=deque)


class RateLimit:
    """Sliding-window rate limiter.

    Args:
        per_key: Rate limit per API key. E.g. ``"100/minute"``.
        global_limit: Global rate limit across all keys. E.g. ``"1000/minute"``.
        backend: Storage backend. ``memory`` for single-process,
            ``redis`` for distributed.

    Example:
        ```python
        rl = RateLimit(per_key="100/minute", global_limit="2000/minute")
        allowed = await rl.check(key_id="fmg_key_abc")
        ```
    """

    def __init__(
        self,
        per_key: str | None = None,
        global_limit: str | None = None,
        backend: Literal["memory", "redis"] = "memory",
    ) -> None:
        self._per_key_count, self._per_key_window = (
            _parse_rate(per_key) if per_key else (None, None)
        )
        self._global_count, self._global_window = (
            _parse_rate(global_limit) if global_limit else (None, None)
        )
        self._backend = backend

        # In-memory state
        self._key_windows: dict[str, _Window] = defaultdict(_Window)
        self._global_window_state = _Window()
        # Serialize check+record so concurrent requests can't burst past a limit.
        self._lock = asyncio.Lock()

    def _slide(self, window: _Window, window_seconds: int, now: float) -> int:
        """Remove expired entries and return current count."""
        cutoff = now - window_seconds
        while window.timestamps and window.timestamps[0] < cutoff:
            window.timestamps.popleft()
        return len(window.timestamps)

    async def check(self, key_id: str) -> bool:
        """Check if a request from ``key_id`` is within limits.

        Returns ``True`` if allowed, ``False`` if rate-limited.
        Records the request if allowed. The check and the record are performed
        atomically under a lock so concurrent callers cannot burst past a limit.
        """
        async with self._lock:
            now = time.monotonic()

            if self._per_key_count is not None and self._per_key_window is not None:
                w = self._key_windows[key_id]
                count = self._slide(w, self._per_key_window, now)
                if count >= self._per_key_count:
                    return False

            if self._global_count is not None and self._global_window is not None:
                gcount = self._slide(
                    self._global_window_state, self._global_window, now
                )
                if gcount >= self._global_count:
                    return False

            # Both limits passed — record against each active window.
            if self._per_key_count is not None and self._per_key_window is not None:
                self._key_windows[key_id].timestamps.append(now)
            if self._global_count is not None and self._global_window is not None:
                self._global_window_state.timestamps.append(now)

            return True

    def status(self, key_id: str) -> dict:
        """Return rate limit status for a key."""
        now = time.monotonic()
        result: dict = {}

        if self._per_key_count is not None and self._per_key_window is not None:
            w = self._key_windows.get(key_id, _Window())
            used = self._slide(w, self._per_key_window, now)
            result["per_key"] = {
                "limit": self._per_key_count,
                "used": used,
                "remaining": max(0, self._per_key_count - used),
                "window_seconds": self._per_key_window,
            }

        if self._global_count is not None and self._global_window is not None:
            used = self._slide(self._global_window_state, self._global_window, now)
            result["global"] = {
                "limit": self._global_count,
                "used": used,
                "remaining": max(0, self._global_count - used),
                "window_seconds": self._global_window,
            }

        return result

    def reset(self, key_id: str) -> None:
        """Reset rate limit counters for a key."""
        if key_id in self._key_windows:
            del self._key_windows[key_id]
