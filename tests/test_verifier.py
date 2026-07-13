"""Tests for KeyStoreVerifier — correctness and non-blocking auth."""

from __future__ import annotations

import asyncio
import time

from fastmcp_guard.keys.store import KeyStore
from fastmcp_guard.keys.verifier import KeyStoreVerifier


async def test_verify_token_valid() -> None:
    store = KeyStore(backend="memory")
    verifier = KeyStoreVerifier(store)
    key = store.create(name="alice", scopes=["read:data"], metadata={"team": "x"})

    token = await verifier.verify_token(key.token)
    assert token is not None
    assert token.client_id == key.id
    assert token.scopes == ["read:data"]
    assert token.claims["key_name"] == "alice"
    assert token.claims["team"] == "x"


async def test_verify_token_invalid() -> None:
    store = KeyStore(backend="memory")
    verifier = KeyStoreVerifier(store)
    store.create(name="alice")

    assert await verifier.verify_token("fmg_sk_bad.token") is None
    assert await verifier.verify_token("not-a-token") is None


async def test_verify_token_does_not_block_event_loop(monkeypatch) -> None:
    """Concurrent verifications must not stall the loop.

    We replace the (normally bcrypt-backed) blocking verify with a 50 ms sleep
    and confirm a background ticker keeps advancing while several verifications
    run — which is only possible if the blocking work is off the event loop.
    """
    store = KeyStore(backend="memory")
    verifier = KeyStoreVerifier(store)
    key = store.create(name="alice")
    real_verify = store.verify

    def slow_verify(token: str):  # noqa: ANN202
        time.sleep(0.05)  # stand-in for the bcrypt + IO cost
        return real_verify(token)

    monkeypatch.setattr(store, "verify", slow_verify)

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.001)

    task = asyncio.create_task(ticker())
    await asyncio.sleep(0)  # let the ticker start

    results = await asyncio.gather(
        *[verifier.verify_token(key.token) for _ in range(5)]
    )
    task.cancel()

    assert all(r is not None for r in results)
    # If verify blocked the loop, five 50 ms calls would run back-to-back and the
    # ticker would get ~0 iterations. Off-loop, it gets tens.
    assert ticks >= 10, f"event loop appears blocked (only {ticks} ticks)"
