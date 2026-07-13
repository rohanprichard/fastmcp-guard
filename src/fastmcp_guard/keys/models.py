"""Data models for API keys."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KeyStatus(str, Enum):
    ACTIVE = "active"
    ROTATING = "rotating"   # Old key in grace period post-rotation
    REVOKED = "revoked"


_TOKEN_PREFIX = "fmg_sk_"


def _generate_token() -> tuple[str, str]:
    """Generate a secure API key token and its public lookup selector.

    The token has the form ``fmg_sk_<selector>.<secret>`` where:

    - ``selector`` is a non-secret, indexed handle used to find the one
      candidate key in O(1) at verification time. ``.`` is not part of the
      URL-safe base64 alphabet, so it is an unambiguous separator.
    - ``secret`` is the high-entropy portion that is bcrypt-hashed and never
      stored in plaintext.

    Returns:
        ``(token, selector)`` — the full token (shown once) and its selector.
    """
    selector = secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    return f"{_TOKEN_PREFIX}{selector}.{secret}", selector


def _selector_of(token: str) -> str | None:
    """Extract the selector from a raw token, or ``None`` if malformed."""
    if not token.startswith(_TOKEN_PREFIX):
        return None
    body = token[len(_TOKEN_PREFIX) :]
    selector, sep, secret = body.partition(".")
    if not sep or not selector or not secret:
        return None
    return selector


class APIKey(BaseModel):
    """An API key issued by fastmcp-guard.

    Attributes:
        id: Unique key identifier (e.g. ``fmg_key_abc123``).
        token: The full secret token shown ONCE at creation.
            Stored as a bcrypt hash after that — never retrievable again.
        token_hash: bcrypt hash of the token stored in the key store.
        name: Human-readable label (e.g. ``alice``, ``ci-bot``).
        scopes: OAuth-style scopes granted to this key.
        status: ``active`` | ``rotating`` | ``revoked``.
        metadata: Arbitrary caller-supplied key/value pairs.
        created_at: UTC timestamp of creation.
        expires_at: Optional expiry. ``None`` means never.
        last_used_at: Last time this key authenticated successfully.
        rotated_from: ID of the previous key this key replaced.
        grace_until: If rotating, when the old key stops being valid.
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: f"fmg_key_{secrets.token_hex(8)}")
    token: str | None = None           # Only populated at creation, then None
    token_hash: str = ""               # bcrypt hash stored in DB
    selector: str = ""                 # Public, indexed handle for O(1) lookup
    name: str
    scopes: list[str] = Field(default_factory=list)
    status: KeyStatus = KeyStatus.ACTIVE
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    rotated_from: str | None = None
    grace_until: datetime | None = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        active = self.status in (KeyStatus.ACTIVE, KeyStatus.ROTATING)
        return active and not self.is_expired
