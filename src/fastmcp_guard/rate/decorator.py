"""Per-tool rate limit decorator."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable

from fastmcp_guard.rate.limiter import _parse_rate

RATE_LIMIT_ATTR = "__fastmcp_guard_rate_limit__"


def rate_limit(limit: str) -> Callable:
    """Apply a per-tool rate limit on top of any Guard-level limits.

    This decorator marks a tool function with a tighter rate limit. The Guard
    middleware reads the marker (:data:`RATE_LIMIT_ATTR`) and enforces it per
    (key, tool) after the per-key limit.

    Works with both sync and async tools. The limit string is validated
    immediately, so a malformed value raises at decoration time.

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
    _parse_rate(limit)  # validate eagerly; raises ValueError on bad input

    def decorator(fn: Callable) -> Callable:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                return await fn(*args, **kwargs)

            wrapper: Callable = async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                return fn(*args, **kwargs)

            wrapper = sync_wrapper

        setattr(fn, RATE_LIMIT_ATTR, limit)
        setattr(wrapper, RATE_LIMIT_ATTR, limit)
        return wrapper

    return decorator
