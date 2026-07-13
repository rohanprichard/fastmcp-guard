"""Core Guard class — the main entry point for fastmcp-guard."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp_guard.audit.log import AuditLog
from fastmcp_guard.ip.policy import IPPolicy
from fastmcp_guard.keys.store import KeyStore
from fastmcp_guard.keys.verifier import KeyStoreVerifier
from fastmcp_guard.middleware import GuardMiddleware
from fastmcp_guard.rate.limiter import RateLimit

if TYPE_CHECKING:
    from fastmcp import FastMCP


class Guard:
    """Production operations layer for a FastMCP server.

    Wraps a FastMCP server to add:

    - API key management (create, rotate, revoke) via :attr:`keys`
    - Rate limiting (per-key and per-tool)
    - Audit logging (structured records, pluggable backends)
    - IP allowlisting

    Authentication is installed as FastMCP's ``auth`` provider; rate limiting,
    IP policy, and audit logging are installed as a FastMCP middleware. Your
    tool code is not modified.

    Args:
        mcp: The FastMCP server instance to protect.
        keys: Key store. Defaults to in-memory (dev only).
        rate_limit: Rate limiting configuration. Disabled by default.
        audit: Audit log configuration. Disabled by default.
        ip: IP policy configuration. Disabled by default.

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp_guard import Guard, KeyStore, RateLimit, AuditLog

        mcp = FastMCP("my-server")
        guard = Guard(
            mcp,
            keys=KeyStore(backend="sqlite", path="keys.db"),
            rate_limit=RateLimit(per_key="100/minute"),
            audit=AuditLog(backend="file", path="audit.jsonl"),
        )
        key = guard.keys.create(name="alice", scopes=["read:data"])
        print(key.token)  # fmg_sk_...  (shown once)
        ```
    """

    def __init__(
        self,
        mcp: FastMCP,
        keys: KeyStore | None = None,
        rate_limit: RateLimit | None = None,
        audit: AuditLog | None = None,
        ip: IPPolicy | None = None,
        manage_auth: bool | None = None,
    ) -> None:
        self._mcp = mcp
        self.keys: KeyStore = keys or KeyStore(backend="memory")
        self._rate_limit = rate_limit
        self._audit = audit
        self._ip = ip
        self._manage_auth = manage_auth

        self._install()

    def _install(self) -> None:
        """Install auth (token verification) and the ops middleware.

        Whether fastmcp-guard manages authentication is controlled by
        ``manage_auth``:

        - ``True``: always install the API-key ``TokenVerifier``.
        - ``False``: never touch ``mcp.auth`` — use this to layer audit / rate
          limiting / IP policy on top of your own OAuth or JWT auth. The audit
          and rate-limit features attribute calls to whatever access token your
          existing auth produces.
        - ``None`` (default): install the API-key verifier only if the server
          has no auth configured yet, so an existing OAuth/JWT setup is
          preserved.
        """
        if self._should_manage_auth():
            self._mcp.auth = KeyStoreVerifier(key_store=self.keys)
        self._mcp.add_middleware(
            GuardMiddleware(
                rate_limit=self._rate_limit,
                audit=self._audit,
                ip=self._ip,
            )
        )

    def _should_manage_auth(self) -> bool:
        if self._manage_auth is not None:
            return self._manage_auth
        return getattr(self._mcp, "auth", None) is None
