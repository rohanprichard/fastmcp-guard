"""API key store — CRUD + lookup with pluggable backends."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastmcp_guard.keys.models import (
    APIKey,
    KeyStatus,
    _generate_token,
    _selector_of,
)


class KeyStore:
    """Manages the lifecycle of API keys.

    Supports multiple storage backends:

    - ``memory``: In-process dict. Fast, no deps, lost on restart. Dev only.
    - ``sqlite``: SQLite database. Persistent, zero-config, single-server.
    - ``postgres`` / ``redis``: planned, not yet implemented.

    Verification is O(1): each token carries a public *selector* used to fetch
    the single candidate key, which is then checked with one bcrypt comparison.

    Args:
        backend: Storage backend to use.
        path: File path for the SQLite backend.
        dsn: Connection string for Postgres/Redis backends (reserved).

    Example:
        ```python
        store = KeyStore(backend="sqlite", path="keys.db")
        key = store.create(name="alice", scopes=["read:data"])
        print(key.token)  # fmg_sk_...  (only shown once)

        verified = store.verify(key.token)
        if verified:
            print(verified.name, verified.scopes)
        ```
    """

    def __init__(
        self,
        backend: Literal["memory", "sqlite", "postgres", "redis"] = "memory",
        path: str | None = None,
        dsn: str | None = None,
    ) -> None:
        self.backend = backend
        self._path = path
        self._dsn = dsn
        self._backend = self._init_backend()

    def _init_backend(self):
        if self.backend == "memory":
            from fastmcp_guard.keys.backends.memory import MemoryKeyBackend

            return MemoryKeyBackend()
        if self.backend == "sqlite":
            from fastmcp_guard.keys.backends.sqlite import SQLiteKeyBackend

            return SQLiteKeyBackend(path=self._path or "fastmcp-guard-keys.db")
        raise NotImplementedError(
            f"The {self.backend!r} key backend is not implemented yet. "
            "Use 'memory' or 'sqlite'."
        )

    def create(
        self,
        name: str,
        scopes: list[str] | None = None,
        expires_in_days: int | None = None,
        metadata: dict | None = None,
    ) -> APIKey:
        """Create a new API key.

        The ``token`` field is populated on the returned object — this is the
        ONLY time it is available in plaintext. Store it securely.

        Args:
            name: Human-readable label for the key.
            scopes: OAuth-style scopes. Defaults to ``[]``.
            expires_in_days: Optional expiry in days from now.
            metadata: Arbitrary metadata dict attached to the key.

        Returns:
            APIKey with ``token`` populated.
        """
        import bcrypt

        token, selector = _generate_token()
        token_hash = bcrypt.hashpw(token.encode(), bcrypt.gensalt()).decode()

        key = APIKey(
            name=name,
            token=token,
            token_hash=token_hash,
            selector=selector,
            scopes=scopes or [],
            metadata=metadata or {},
            expires_at=(
                datetime.now(timezone.utc) + timedelta(days=expires_in_days)
                if expires_in_days
                else None
            ),
        )

        self._backend.add(key)
        return key

    def verify(self, token: str) -> APIKey | None:
        """Verify a raw token and return the matching APIKey, or None.

        O(1): the token's selector fetches a single candidate, which is then
        checked with one bcrypt comparison. Rotating keys whose grace period
        has elapsed are finalized (revoked) lazily here.

        Args:
            token: The raw ``fmg_sk_...`` token from the Authorization header.

        Returns:
            The matching ``APIKey`` (token stripped) if valid, else ``None``.
        """
        import bcrypt

        selector = _selector_of(token)
        if selector is None:
            return None

        key = self._backend.get_by_selector(selector)
        if key is None:
            return None

        # Finalize an elapsed grace period before validity checks.
        if (
            key.status == KeyStatus.ROTATING
            and key.grace_until is not None
            and datetime.now(timezone.utc) > key.grace_until
        ):
            key.status = KeyStatus.REVOKED
            self._backend.update(key)

        if not key.is_valid:
            return None

        try:
            if not bcrypt.checkpw(token.encode(), key.token_hash.encode()):
                return None
        except (ValueError, TypeError):
            return None

        key.last_used_at = datetime.now(timezone.utc)
        self._backend.update(key)
        return key.model_copy(update={"token": None})

    def get(self, key_id: str) -> APIKey | None:
        """Get a key by ID (token not included)."""
        key = self._backend.get_by_id(key_id)
        return key.model_copy(update={"token": None}) if key else None

    def list(self, include_revoked: bool = False) -> list[APIKey]:
        """List all keys (tokens not included).

        Args:
            include_revoked: Include revoked keys in the result.
        """
        keys = [k.model_copy(update={"token": None}) for k in self._backend.all()]
        if not include_revoked:
            keys = [k for k in keys if k.status != KeyStatus.REVOKED]
        return sorted(keys, key=lambda k: k.created_at)

    def rotate(self, key_id: str, grace_period_hours: int = 24) -> APIKey:
        """Rotate a key. Returns a new key; old key stays valid for the grace period.

        Args:
            key_id: ID of the key to rotate.
            grace_period_hours: Hours the old key remains valid after rotation.
                Defaults to 24 hours. Set to 0 for immediate revocation.

        Returns:
            New ``APIKey`` with ``token`` populated.

        Raises:
            KeyError: If the key is not found.
            ValueError: If the key is already revoked.
        """
        old_key = self._backend.get_by_id(key_id)
        if old_key is None:
            raise KeyError(f"Key not found: {key_id}")
        if old_key.status == KeyStatus.REVOKED:
            raise ValueError(f"Cannot rotate a revoked key: {key_id}")

        old_key.status = KeyStatus.ROTATING
        old_key.grace_until = datetime.now(timezone.utc) + timedelta(
            hours=grace_period_hours
        )
        self._backend.update(old_key)

        new_key = self.create(
            name=old_key.name,
            scopes=old_key.scopes,
            metadata=old_key.metadata,
        )
        new_key.rotated_from = key_id
        self._backend.update(new_key)
        return new_key

    def revoke(self, key_id: str) -> None:
        """Immediately revoke a key.

        Args:
            key_id: ID of the key to revoke.

        Raises:
            KeyError: If the key is not found.
        """
        key = self._backend.get_by_id(key_id)
        if key is None:
            raise KeyError(f"Key not found: {key_id}")
        key.status = KeyStatus.REVOKED
        self._backend.update(key)

    def _expire_grace_periods(self) -> None:
        """Finalize all rotating keys whose grace period has elapsed.

        Verification also does this lazily; this method exists for an optional
        periodic sweep.
        """
        now = datetime.now(timezone.utc)
        for key in self._backend.all():
            if (
                key.status == KeyStatus.ROTATING
                and key.grace_until
                and now > key.grace_until
            ):
                key.status = KeyStatus.REVOKED
                self._backend.update(key)
