"""Tests for rate limiting."""

import pytest

from fastmcp_guard.rate.limiter import RateLimit, _parse_rate


def test_parse_rate_minute():
    count, seconds = _parse_rate("100/minute")
    assert count == 100
    assert seconds == 60


def test_parse_rate_second():
    count, seconds = _parse_rate("10/second")
    assert count == 10
    assert seconds == 1


def test_parse_rate_hour():
    count, seconds = _parse_rate("1000/hour")
    assert count == 1000
    assert seconds == 3600


def test_parse_rate_day():
    count, seconds = _parse_rate("50000/day")
    assert count == 50000
    assert seconds == 86400


def test_parse_rate_invalid():
    with pytest.raises(ValueError):
        _parse_rate("100 per minute")
    with pytest.raises(ValueError):
        _parse_rate("fast")


@pytest.mark.asyncio
async def test_per_key_allows_within_limit():
    rl = RateLimit(per_key="5/minute")
    for _ in range(5):
        assert await rl.check(key_id="key1") is True


@pytest.mark.asyncio
async def test_per_key_blocks_over_limit():
    rl = RateLimit(per_key="3/minute")
    for _ in range(3):
        await rl.check(key_id="key1")
    assert await rl.check(key_id="key1") is False


@pytest.mark.asyncio
async def test_per_key_independent_between_keys():
    rl = RateLimit(per_key="2/minute")
    await rl.check(key_id="key1")
    await rl.check(key_id="key1")
    # key1 is at limit
    assert await rl.check(key_id="key1") is False
    # key2 is independent
    assert await rl.check(key_id="key2") is True


@pytest.mark.asyncio
async def test_global_limit():
    rl = RateLimit(global_limit="3/minute")
    assert await rl.check(key_id="key1") is True
    assert await rl.check(key_id="key2") is True
    assert await rl.check(key_id="key3") is True
    assert await rl.check(key_id="key4") is False


@pytest.mark.asyncio
async def test_reset_clears_per_key():
    rl = RateLimit(per_key="2/minute")
    await rl.check(key_id="key1")
    await rl.check(key_id="key1")
    assert await rl.check(key_id="key1") is False

    rl.reset("key1")
    assert await rl.check(key_id="key1") is True


@pytest.mark.asyncio
async def test_status_returns_usage():
    rl = RateLimit(per_key="10/minute")
    await rl.check(key_id="key1")
    await rl.check(key_id="key1")

    status = rl.status("key1")
    assert status["per_key"]["used"] == 2
    assert status["per_key"]["remaining"] == 8
    assert status["per_key"]["limit"] == 10
