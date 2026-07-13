"""FastMCP middleware that enforces fastmcp-guard's ops controls.

Registered on the server via ``add_middleware``, this wraps every tool call to:

- enforce the IP allow/deny policy (when a client IP is available),
- apply per-key and per-tool rate limits keyed by the authenticated identity,
- write a structured audit record for the call.

Authentication (token -> identity) is handled separately by
:class:`~fastmcp_guard.keys.verifier.KeyStoreVerifier`; this middleware reads the
resulting access token to attribute calls to a key.
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware import Middleware

from fastmcp_guard.audit.log import AuditRecord
from fastmcp_guard.rate.decorator import RATE_LIMIT_ATTR
from fastmcp_guard.rate.limiter import RateLimit

if TYPE_CHECKING:
    from fastmcp.server.middleware import CallNext, MiddlewareContext

    from fastmcp_guard.audit.log import AuditLog
    from fastmcp_guard.ip.policy import IPPolicy

_ANON = "anonymous"


def _output_preview(result: Any, limit: int = 200) -> str | None:
    """Best-effort short string preview of a tool result."""
    if result is None:
        return None
    try:
        text = getattr(result, "content", None)
        rendered = str(text if text is not None else result)
    except Exception:
        return None
    return rendered[:limit]


class GuardMiddleware(Middleware):
    """Enforces IP policy, rate limits, and audit logging on tool calls."""

    def __init__(
        self,
        rate_limit: RateLimit | None = None,
        audit: AuditLog | None = None,
        ip: IPPolicy | None = None,
    ) -> None:
        self._rate_limit = rate_limit
        self._audit = audit
        self._ip = ip
        # Lazily-built per-tool limiters, keyed by the tool's limit string.
        self._tool_limiters: dict[str, RateLimit] = {}

    # -- identity / context helpers -----------------------------------------

    @staticmethod
    def _identity() -> tuple[str, str, list[str], dict]:
        """Return (key_id, key_name, scopes, metadata) for the caller."""
        try:
            from fastmcp.server.dependencies import get_access_token

            token = get_access_token()
        except Exception:
            token = None
        if token is None:
            return "", "", [], {}
        claims = dict(getattr(token, "claims", {}) or {})
        key_name = claims.pop("key_name", "")
        claims.pop("key_id", None)
        return (
            getattr(token, "client_id", "") or "",
            key_name,
            list(getattr(token, "scopes", []) or []),
            claims,
        )

    @staticmethod
    def _client_ip() -> str | None:
        try:
            from fastmcp.server.dependencies import get_http_request

            request = get_http_request()
        except Exception:
            return None
        client = getattr(request, "client", None)
        return getattr(client, "host", None) if client else None

    async def _tool_limit(
        self, context: MiddlewareContext, tool_name: str
    ) -> str | None:
        """Read a per-tool ``@rate_limit`` marker, if any."""
        try:
            server = context.fastmcp_context.fastmcp
            tool = await server.get_tool(tool_name)
            return getattr(tool.fn, RATE_LIMIT_ATTR, None)
        except Exception:
            return None

    def _limiter_for(self, limit: str) -> RateLimit:
        limiter = self._tool_limiters.get(limit)
        if limiter is None:
            limiter = RateLimit(per_key=limit)
            self._tool_limiters[limit] = limiter
        return limiter

    async def _write_audit(self, record: AuditRecord) -> None:
        if self._audit is None:
            return
        # Audit must never break the request path.
        with contextlib.suppress(Exception):
            await self._audit.write(record)

    # -- main hook ----------------------------------------------------------

    async def on_call_tool(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        from fastmcp.exceptions import ToolError

        params = context.message
        tool_name = getattr(params, "name", "") or ""
        args = getattr(params, "arguments", None) or {}

        key_id, key_name, scopes, metadata = self._identity()
        client_ip = self._client_ip()
        rate_id = key_id or _ANON

        def record(status: str, duration_ms: float = 0.0, error: str | None = None,
                   output: Any = None) -> AuditRecord:
            return AuditRecord(
                key_id=key_id, key_name=key_name, tool=tool_name, scopes=scopes,
                duration_ms=duration_ms, status=status, error=error,
                input_args=dict(args) if args else None,
                output_preview=_output_preview(output), client_ip=client_ip,
                metadata=metadata,
            )

        # 1. IP policy
        if (
            self._ip is not None
            and client_ip is not None
            and not self._ip.is_allowed(client_ip)
        ):
            await self._write_audit(record("unauthorized"))
            raise ToolError("Access denied for your IP address")

        # 2. Per-key rate limit
        if self._rate_limit is not None and not await self._rate_limit.check(rate_id):
            await self._write_audit(record("rate_limited"))
            raise ToolError("Rate limit exceeded")

        # 3. Per-tool rate limit
        tool_limit = await self._tool_limit(context, tool_name)
        if tool_limit is not None:
            limiter = self._limiter_for(tool_limit)
            if not await limiter.check(f"{rate_id}:{tool_name}"):
                await self._write_audit(record("rate_limited"))
                raise ToolError(f"Rate limit exceeded for tool: {tool_name}")

        # 4. Execute + audit
        start = time.perf_counter()
        status, error, result = "ok", None, None
        try:
            result = await call_next(context)
            return result
        except Exception as exc:
            status, error = "error", str(exc)
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            await self._write_audit(record(status, duration_ms, error, result))
