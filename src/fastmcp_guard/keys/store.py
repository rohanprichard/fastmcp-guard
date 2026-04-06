"""API key store — CRUD + lookup with pluggable backends."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastmcp_guard.keys.models import APIKey, KeyStatus, _generate_token


class KeyStore:
    """Manages the lifecycle of API keys.

    Supports multiple storage backends:
    - ``memory``: In-process dict. Fast, no deps, lost on restart. Dev only.
    - ``sqlite``: SQLite database. Persistent, zero-config, single-server.
    - ``postgres``: PostgreSQL. Multi-server HA deployments.
    - ``redis``: Redis. High-throughput + integrated rate limiting.

    Args:
        backend: Storage backend to use.
        path: File path for SQLite backend.
        dsn: Connection string for Postgres/Redis backends.

    Example:
        ```python
        store = KeyStore(backend="sqlite", path="keys.db")
        key = store.create(name="alice", scopes=["read:data"])
        print(key.token)  # fmg_sk_...  (only shown once)

        # Later — verify an incoming token
        verified = store.verify("fmg_sk_...")
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

        # In-memory store (real backends implemented in subclasses)
        # Maps token_hash -> APIKey
        self._store: dict[str, APIKey] = {}

        if backend != "memory":
            self._init_backend()

    def _init_backend(self) -> None:
        """Initialise the selected persistent backend."""
        if self.backend == "sqlite":
            from fastmcp_guard.keys.backends.sqlite import SQLiteBackend
            self._backend = SQLiteBackend(path=self._path or "fastmcp-guard-keys.db")
        elif self.backend == "postgres":
            from fastmcp_guard.keys.backends.postgres import PostgresBackend
            if not self._dsn:
                raise ValueError("dsn required for postgres backend")
            self._backend = PostgresBackend(dsn=self._dsn)
        elif self.backend == "redis":
            from fastmcp_guard.keys.backends.redis import RedisBackend
            if not self._dsn:
                raise ValueError("dsn required for redis backend")
            self._backend = RedisBackend(dsn=self._dsn)

    def create(
        self,
        name: str,
        scopes: list[str] | None = None,
        expires_in_days: int | None = None,
        metadata: dict | None = None,
    ) -> APIKey:
        """Create a new API key.

        The ``token`` field is populated on the returned object — this is the
        ONLY time it is available in plaintext. Store it securely. Subsequent
        calls to ``get`` or ``list`` will NOT return the token.

        Args:
            name: Human-readable label for the key.
            scopes: OAuth-style scopes. Defaults to ``[]`` (no access).
            expires_in_days: Optional expiry in days from now.
            metadata: Arbitrary metadata dict attached to the key.

        Returns:
            APIKey with ``token`` populated.
        """
        import bcrypt

        token = _generate_token()
        token_hash = bcrypt.hashpw(token.encode(), bcrypt.gensalt()).decode()

        key = APIKey(
            name=name,
            token=token,
            token_hash=token_hash,
            scopes=scopes or [],
            metadata=metadata or {},
            expires_at=(
                datetime.now(timezone.utc) + timedelta(days=expires_in_days)
                if expires_in_days
                else None
            ),
        )

        self._store[token_hash] = key
        return key

    def verify(self, token: str) -> APIKey | None:
        """Verify a raw token and return the matching APIKey, or None.

        Updates ``last_used_at`` on successful verification.

        Args:
            token: The raw ``fmg_sk_...`` token from the Authorization header.

        Returns:
            The matching ``APIKey`` if valid, else ``None``.
        """
        import bcrypt

        for key in self._store.values():
            if not key.is_valid:
                continue
            try:
                if bcrypt.checkpw(token.encode(), key.token_hash.encode()):
                    key.last_used_at = datetime.now(timezone.utc)
                    return key
            except Exception:
                continue
        return None

    def get(self, key_id: str) -> APIKey | None:
        """Get a key by ID (token not included)."""
        for key in self._store.values():
            if key.id == key_id:
                masked = key.model_copy(update={"token": None})
                return masked
        return None

    def list(self, include_revoked: bool = False) -> list[APIKey]:
        """List all keys (tokens not included).

        Args:
            include_revoked: Include revoked keys in the result.
        """
        keys = [k.model_copy(update={"token": None}) for k in self._store.values()]
        if not include_revoked:
            keys = [k for k in keys if k.status != KeyStatus.REVOKED]
        return sorted(keys, key=lambda k: k.created_at)

    def rotate(
        self,
        key_id: str,
        grace_period_hours: int = 24,
    ) -> APIKey:
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
        old_key = self.get(key_id)
        if old_key is None:
            raise KeyError(f"Key not found: {key_id}")
        if old_key.status == KeyStatus.REVOKED:
            raise ValueError(f"Cannot rotate a revoked key: {key_id}")

        # Mark old key as rotating with grace period
        for key in self._store.values():
            if key.id == key_id:
                key.status = KeyStatus.ROTATING
                key.grace_until = datetime.now(timezone.utc) + timedelta(hours=grace_period_hours)
                break

        # Create new key with same settings
        new_key = self.create(
            name=old_key.name,
            scopes=old_key.scopes,
            metadata=old_key.metadata,
        )
        # Track lineage
        for key in self._store.values():
            if key.id == new_key.id:
                key.rotated_from = key_id
                break

        return new_key

    def revoke(self, key_id: str) -> None:
        """Immediately revoke a key.

        Args:
            key_id: ID of the key to revoke.

        Raises:
            KeyError: If the key is not found.
        """
        for key in self._store.values():
            if key.id == key_id:
                key.status = KeyStatus.REVOKED
                return
        raise KeyError(f"Key not found: {key_id}")

    def _expire_grace_periods(self) -> None:
        """Called periodically to finalize expired rotating keys."""
        now = datetime.now(timezone.utc)
        for key in self._store.values():
            if key.status == KeyStatus.ROTATING and key.grace_until and now > key.grace_until:
                key.status = KeyStatus.REVOKED
