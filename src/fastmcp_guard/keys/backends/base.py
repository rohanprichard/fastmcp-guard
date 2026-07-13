"""Storage backend protocol for the key store.

A backend persists :class:`~fastmcp_guard.keys.models.APIKey` records and
provides the two lookups the store needs on the hot path:

- ``get_by_selector`` — O(1) lookup by the public, non-secret selector, so that
  ``KeyStore.verify`` only performs a single bcrypt check.
- ``get_by_id`` — lookup by key id for administrative operations.

Backends never store the plaintext ``token`` — only its bcrypt ``token_hash``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastmcp_guard.keys.models import APIKey


@runtime_checkable
class KeyBackend(Protocol):
    """Persistence interface for API keys."""

    def add(self, key: APIKey) -> None:
        """Persist a newly created key (without its plaintext token)."""
        ...

    def update(self, key: APIKey) -> None:
        """Persist mutable fields of an existing key (status, timestamps, …)."""
        ...

    def get_by_id(self, key_id: str) -> APIKey | None:
        """Return the key with this id, or ``None``."""
        ...

    def get_by_selector(self, selector: str) -> APIKey | None:
        """Return the key with this selector, or ``None`` (O(1))."""
        ...

    def all(self) -> list[APIKey]:
        """Return every stored key."""
        ...
