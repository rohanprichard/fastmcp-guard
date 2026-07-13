"""In-memory key backend. Fast, no dependencies, lost on restart. Dev only."""

from __future__ import annotations

from fastmcp_guard.keys.models import APIKey


class MemoryKeyBackend:
    """Stores keys in process memory, indexed by id and selector."""

    def __init__(self) -> None:
        self._by_id: dict[str, APIKey] = {}
        self._selector_to_id: dict[str, str] = {}

    def _store(self, key: APIKey) -> APIKey:
        # Never keep the plaintext token in the store.
        return key.model_copy(update={"token": None})

    def add(self, key: APIKey) -> None:
        self._by_id[key.id] = self._store(key)
        if key.selector:
            self._selector_to_id[key.selector] = key.id

    def update(self, key: APIKey) -> None:
        self._by_id[key.id] = self._store(key)
        if key.selector:
            self._selector_to_id[key.selector] = key.id

    def get_by_id(self, key_id: str) -> APIKey | None:
        stored = self._by_id.get(key_id)
        return stored.model_copy() if stored else None

    def get_by_selector(self, selector: str) -> APIKey | None:
        key_id = self._selector_to_id.get(selector)
        if key_id is None:
            return None
        stored = self._by_id.get(key_id)
        return stored.model_copy() if stored else None

    def all(self) -> list[APIKey]:
        return [k.model_copy() for k in self._by_id.values()]
