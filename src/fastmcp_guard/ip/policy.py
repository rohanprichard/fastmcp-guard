"""IP allowlist / denylist policy."""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence


class IPPolicy:
    """Restrict access by client IP address.

    Supports both individual IPs and CIDR ranges.
    If ``allow`` is specified, ONLY those IPs/ranges pass.
    If ``deny`` is specified, those IPs/ranges are blocked (even if in allow).

    Args:
        allow: Allowlist of IPs/CIDR ranges. If empty, all IPs are allowed.
        deny: Denylist of IPs/CIDR ranges. Applied after allow check.

    Example:
        ```python
        policy = IPPolicy(
            allow=["10.0.0.0/8", "192.168.1.100"],
            deny=["10.99.0.0/16"],  # block a specific subnet within allowlist
        )
        assert policy.is_allowed("10.0.1.5") is True
        assert policy.is_allowed("10.99.0.1") is False
        assert policy.is_allowed("8.8.8.8") is False
        ```
    """

    def __init__(
        self,
        allow: Sequence[str] | None = None,
        deny: Sequence[str] | None = None,
    ) -> None:
        self._allow = [ipaddress.ip_network(ip, strict=False) for ip in (allow or [])]
        self._deny = [ipaddress.ip_network(ip, strict=False) for ip in (deny or [])]

    def is_allowed(self, ip: str) -> bool:
        """Return True if the IP is permitted by this policy."""
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False

        # Check denylist first
        for net in self._deny:
            if addr in net:
                return False

        # If no allowlist, everything not denied is allowed
        if not self._allow:
            return True

        # Check allowlist
        return any(addr in net for net in self._allow)
