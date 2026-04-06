"""Per-tool rate limit decorator."""

from __future__ import annotations

import functools
from typing import Callable


def rate_limit(limit: str) -> Callable:
    """Apply a per-tool rate limit on top of any Guard-level limits.

    This decorator marks a tool function with a tighter rate limit.
    The Guard middleware reads this marker and applies it after the
    per-key limit.

    Args:
        limit: Rate string, e.g. ``"10/minute"``.

    Example:
        ```python
        from fastmcp_guard.rate import rate_limit

        @mcp.tool
        @rate_limit("10/minute")
        def run_expensive_analysis(data: str) -> str:
            ...
        ```
    """
    def decorator(fn: Callable) -> Callable:
        # Attach metadata for the Guard middleware to read
        fn.__fastmcp_guard_rate_limit__ = limit

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)

        wrapper.__fastmcp_guard_rate_limit__ = limit
        return wrapper

    return decorator
