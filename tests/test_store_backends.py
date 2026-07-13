"""KeyStore tests across both real backends (memory + sqlite)."""

from __future__ import annotations

import time

import pytest

from fastmcp_guard.keys.models import KeyStatus, _selector_of
from fastmcp_guard.keys.store import KeyStore


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path) -> KeyStore:
    if request.param == "memory":
        return KeyStore(backend="memory")
    return KeyStore(backend="sqlite", path=str(tmp_path / "keys.db"))


def test_create_and_verify(store: KeyStore) -> None:
    key = store.create(name="alice", scopes=["read:data"], metadata={"team": "x"})
    assert key.token and "." in key.token
    assert key.selector and key.selector in key.token

    verified = store.verify(key.token)
    assert verified is not None
    assert verified.name == "alice"
    assert verified.scopes == ["read:data"]
    assert verified.metadata == {"team": "x"}
    assert verified.token is None  # never leaked back
    assert verified.last_used_at is not None


def test_verify_rejects_bad_tokens(store: KeyStore) -> None:
    store.create(name="alice")
    assert store.verify("not-a-token") is None
    assert store.verify("fmg_sk_deadbeef.wrongsecret") is None
    assert store.verify("fmg_sk_missing_separator") is None


def test_selector_is_extractable() -> None:
    assert _selector_of("fmg_sk_abcd.secret") == "abcd"
    assert _selector_of("bad") is None
    assert _selector_of("fmg_sk_noseparator") is None


def test_list_masks_tokens(store: KeyStore) -> None:
    store.create(name="a")
    store.create(name="b")
    keys = store.list()
    assert len(keys) == 2
    assert all(k.token is None for k in keys)


def test_rotate_grace_period(store: KeyStore) -> None:
    key = store.create(name="alice", scopes=["read"])
    new_key = store.rotate(key.id, grace_period_hours=24)
    # Old key still valid during grace; new key valid; lineage tracked.
    assert store.verify(key.token) is not None
    assert store.verify(new_key.token) is not None
    assert new_key.rotated_from == key.id
    assert new_key.scopes == ["read"]


def test_rotate_zero_grace_revokes_old_on_verify(store: KeyStore) -> None:
    key = store.create(name="alice")
    store.rotate(key.id, grace_period_hours=0)
    time.sleep(0.01)
    assert store.verify(key.token) is None  # grace elapsed -> revoked lazily


def test_revoke(store: KeyStore) -> None:
    key = store.create(name="alice")
    store.revoke(key.id)
    assert store.verify(key.token) is None
    assert store.get(key.id).status == KeyStatus.REVOKED


def test_rotate_revoked_raises(store: KeyStore) -> None:
    key = store.create(name="alice")
    store.revoke(key.id)
    with pytest.raises(ValueError):
        store.rotate(key.id)


def test_expiry(store: KeyStore) -> None:
    key = store.create(name="short", expires_in_days=-1)  # already expired
    assert store.verify(key.token) is None


def test_unimplemented_backend_raises() -> None:
    with pytest.raises(NotImplementedError):
        KeyStore(backend="postgres")


def test_sqlite_persists_across_instances(tmp_path) -> None:
    path = str(tmp_path / "persist.db")
    s1 = KeyStore(backend="sqlite", path=path)
    key = s1.create(name="alice", scopes=["read"])
    token = key.token

    s2 = KeyStore(backend="sqlite", path=path)  # fresh instance, same file
    verified = s2.verify(token)
    assert verified is not None and verified.name == "alice"
