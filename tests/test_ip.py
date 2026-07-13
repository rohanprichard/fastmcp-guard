"""Tests for IP policy."""

from fastmcp_guard.ip.policy import IPPolicy


def test_no_policy_allows_all():
    policy = IPPolicy()
    assert policy.is_allowed("8.8.8.8") is True
    assert policy.is_allowed("10.0.0.1") is True


def test_allowlist_permits_matching():
    policy = IPPolicy(allow=["10.0.0.0/8"])
    assert policy.is_allowed("10.0.1.5") is True
    assert policy.is_allowed("10.255.255.255") is True


def test_allowlist_blocks_non_matching():
    policy = IPPolicy(allow=["10.0.0.0/8"])
    assert policy.is_allowed("8.8.8.8") is False
    assert policy.is_allowed("192.168.1.1") is False


def test_allowlist_single_ip():
    policy = IPPolicy(allow=["192.168.1.100"])
    assert policy.is_allowed("192.168.1.100") is True
    assert policy.is_allowed("192.168.1.101") is False


def test_denylist_blocks_matching():
    policy = IPPolicy(deny=["203.0.113.0/24"])
    assert policy.is_allowed("203.0.113.5") is False
    assert policy.is_allowed("8.8.8.8") is True


def test_deny_takes_priority_over_allow():
    policy = IPPolicy(
        allow=["10.0.0.0/8"],
        deny=["10.99.0.0/16"],
    )
    assert policy.is_allowed("10.0.1.5") is True
    assert policy.is_allowed("10.99.0.1") is False


def test_invalid_ip_returns_false():
    policy = IPPolicy(allow=["10.0.0.0/8"])
    assert policy.is_allowed("not-an-ip") is False
    assert policy.is_allowed("") is False
