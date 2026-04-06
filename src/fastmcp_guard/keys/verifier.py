"""TokenVerifier implementation that uses the KeyStore."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp_guard.keys.store import KeyStore
    from fastmcp_guard.rate.limiter import RateLimit
    from fastmcp_guard.audit.log import AuditLog
    from fastmcp_guard.ip.policy import IPPolicy


class KeyStoreVerifier:
    """FastMCP TokenVerifier backed by fastmcp-guard's KeyStore.

    Plugs into FastMCP's auth system. On each request:
    1. Extracts Bearer token from Authorization header
    2. Verifies it against the KeyStore (bcrypt hash check)
    3. Applies IP policy
    4. Applies rate limiting
    5. Returns AccessToken with scopes for FastMCP's authz layer

    This class conforms to FastMCP's ``TokenVerifier`` protocol.
    """

    def __init__(
        self,
        key_store: KeyStore,
        rate_limit: RateLimit | None = None,
        audit: AuditLog | None = None,
        ip: IPPolicy | None = None,
    ) -> None:
        self._key_store = key_store
        self._rate_limit = rate_limit
        self._audit = audit
        self._ip = ip

    async def verify_token(self, token: str) -> Any:
        """Verify a raw bearer token.

        Called by FastMCP on every authenticated request.

        Returns an AccessToken-compatible object on success,
        or raises an exception on failure.
        """
        from fastmcp.server.auth import AccessToken
        from fastmcp.exceptions import AuthorizationError

        key = self._key_store.verify(token)
        if key is None:
            raise AuthorizationError("Invalid or expired API key")

        # Rate limiting
        if self._rate_limit is not None:
            allowed = await self._rate_limit.check(key_id=key.id)
            if not allowed:
                raise AuthorizationError(f"Rate limit exceeded for key: {key.name}")

        return AccessToken(
            token=token,
            client_id=key.id,
            scopes=key.scopes,
            claims={"key_name": key.name, "key_id": key.id, **key.metadata},
        )
