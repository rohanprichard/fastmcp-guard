"""Tests for API key lifecycle."""

import pytest

from fastmcp_guard.keys.models import KeyStatus
from fastmcp_guard.keys.store import KeyStore


@pytest.fixture
def store():
    return KeyStore(backend="memory")


def test_create_key(store):
    key = store.create(name="alice", scopes=["read:data"])
    assert key.token is not None
    assert key.token.startswith("fmg_sk_")
    assert key.name == "alice"
    assert key.scopes == ["read:data"]
    assert key.status == KeyStatus.ACTIVE


def test_verify_valid_token(store):
    key = store.create(name="alice", scopes=["read:data"])
    token = key.token

    verified = store.verify(token)
    assert verified is not None
    assert verified.name == "alice"
    assert verified.scopes == ["read:data"]


def test_verify_invalid_token(store):
    store.create(name="alice")
    result = store.verify("fmg_sk_thisiswrong")
    assert result is None


def test_verify_updates_last_used(store):
    key = store.create(name="alice")
    assert key.last_used_at is None

    verified = store.verify(key.token)
    assert verified.last_used_at is not None


def test_list_keys(store):
    store.create(name="alice")
    store.create(name="bob")

    keys = store.list()
    assert len(keys) == 2
    names = {k.name for k in keys}
    assert names == {"alice", "bob"}


def test_list_excludes_token(store):
    store.create(name="alice")
    keys = store.list()
    for k in keys:
        assert k.token is None


def test_revoke_key(store):
    key = store.create(name="alice")
    token = key.token

    store.revoke(key.id)

    assert store.verify(token) is None
    k = store.get(key.id)
    assert k.status == KeyStatus.REVOKED


def test_revoke_missing_key(store):
    with pytest.raises(KeyError):
        store.revoke("fmg_key_doesnotexist")


def test_rotate_key(store):
    old_key = store.create(name="alice", scopes=["read:data"])
    old_token = old_key.token

    new_key = store.rotate(old_key.id, grace_period_hours=24)

    # New key works
    assert store.verify(new_key.token) is not None

    # Old key still works (grace period)
    assert store.verify(old_token) is not None

    # Old key is in rotating status
    old = store.get(old_key.id)
    assert old.status == KeyStatus.ROTATING


def test_rotate_revoked_key_raises(store):
    key = store.create(name="alice")
    store.revoke(key.id)

    with pytest.raises(ValueError, match="revoked"):
        store.rotate(key.id)


def test_list_excludes_revoked_by_default(store):
    key = store.create(name="alice")
    store.revoke(key.id)
    store.create(name="bob")

    keys = store.list()
    assert len(keys) == 1
    assert keys[0].name == "bob"


def test_list_includes_revoked_when_requested(store):
    key = store.create(name="alice")
    store.revoke(key.id)
    store.create(name="bob")

    keys = store.list(include_revoked=True)
    assert len(keys) == 2


def test_key_metadata(store):
    key = store.create(name="ci-bot", metadata={"team": "eng", "env": "prod"})
    retrieved = store.get(key.id)
    assert retrieved.metadata == {"team": "eng", "env": "prod"}
