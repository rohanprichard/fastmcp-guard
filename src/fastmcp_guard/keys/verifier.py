"""TokenVerifier implementation that authenticates against the KeyStore."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastmcp.server.auth import AccessToken, TokenVerifier

if TYPE_CHECKING:
    from fastmcp_guard.keys.store import KeyStore


class KeyStoreVerifier(TokenVerifier):
    """FastMCP ``TokenVerifier`` backed by fastmcp-guard's :class:`KeyStore`.

    On each authenticated request FastMCP calls :meth:`verify_token` with the
    raw Bearer token. We look it up in the key store (O(1) selector lookup +
    single bcrypt check) and, on success, return an ``AccessToken`` carrying the
    key's identity and scopes. Rate limiting, IP policy, and audit logging are
    handled by :class:`~fastmcp_guard.middleware.GuardMiddleware`, not here.
    """

    def __init__(
        self,
        key_store: KeyStore,
        required_scopes: list[str] | None = None,
    ) -> None:
        super().__init__(required_scopes=required_scopes)
        self._key_store = key_store

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return an ``AccessToken`` for a valid token, else ``None``.

        ``KeyStore.verify`` is synchronous and does blocking work — a store
        lookup plus a bcrypt comparison (CPU-bound, tens of milliseconds). We run
        it in a worker thread so it never blocks the event loop; bcrypt releases
        the GIL while hashing, so concurrent verifications run in parallel.
        """
        key = await asyncio.to_thread(self._key_store.verify, token)
        if key is None:
            return None
        return AccessToken(
            token=token,
            client_id=key.id,
            scopes=list(key.scopes),
            claims={"key_name": key.name, "key_id": key.id, **key.metadata},
        )
