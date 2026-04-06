"""Core Guard class — the main entry point for fastmcp-guard."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp_guard.keys.store import KeyStore
from fastmcp_guard.keys.verifier import KeyStoreVerifier
from fastmcp_guard.rate.limiter import RateLimit
from fastmcp_guard.audit.log import AuditLog
from fastmcp_guard.ip.policy import IPPolicy

if TYPE_CHECKING:
    from fastmcp import FastMCP


class Guard:
    """Production operations layer for a FastMCP server.

    Wraps a FastMCP server to add:
    - API key management (create, rotate, revoke)
    - Rate limiting (per-key and global)
    - Audit logging (structured JSONL, pluggable backends)
    - IP allowlisting

    Args:
        mcp: The FastMCP server instance to protect.
        keys: Key store configuration. Defaults to in-memory (dev only).
        rate_limit: Rate limiting configuration. Disabled by default.
        audit: Audit log configuration. Disabled by default.
        ip: IP policy configuration. Disabled by default.

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp_guard import Guard
        from fastmcp_guard.keys import KeyStore
        from fastmcp_guard.rate import RateLimit
        from fastmcp_guard.audit import AuditLog

        mcp = FastMCP("my-server")
        guard = Guard(
            mcp,
            keys=KeyStore(backend="sqlite", path="keys.db"),
            rate_limit=RateLimit(per_key="100/minute"),
            audit=AuditLog(backend="file", path="audit.jsonl"),
        )
        ```
    """

    def __init__(
        self,
        mcp: FastMCP,
        keys: KeyStore | None = None,
        rate_limit: RateLimit | None = None,
        audit: AuditLog | None = None,
        ip: IPPolicy | None = None,
    ) -> None:
        self._mcp = mcp
        self.keys: KeyStore = keys or KeyStore(backend="memory")
        self._rate_limit = rate_limit
        self._audit = audit
        self._ip = ip

        self._install()

    def _install(self) -> None:
        """Install the guard into the FastMCP server."""
        verifier = KeyStoreVerifier(
            key_store=self.keys,
            rate_limit=self._rate_limit,
            audit=self._audit,
            ip=self._ip,
        )
        # Register as FastMCP's auth provider
        self._mcp.auth = verifier  # type: ignore[assignment]
