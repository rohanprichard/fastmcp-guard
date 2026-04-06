"""Data models for API keys."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class KeyStatus(str, Enum):
    ACTIVE = "active"
    ROTATING = "rotating"   # Old key in grace period post-rotation
    REVOKED = "revoked"


def _generate_token() -> str:
    """Generate a secure API key token with a recognisable prefix."""
    return f"fmg_sk_{secrets.token_urlsafe(32)}"


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

    id: str = Field(default_factory=lambda: f"fmg_key_{secrets.token_hex(8)}")
    token: str | None = None           # Only populated at creation, then None
    token_hash: str = ""               # bcrypt hash stored in DB
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
        return self.status in (KeyStatus.ACTIVE, KeyStatus.ROTATING) and not self.is_expired

    class Config:
        use_enum_values = True
