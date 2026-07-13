"""SQLite key backend — persistent, zero-config, single-server."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastmcp_guard.keys.models import APIKey

_COLUMNS = (
    "id",
    "token_hash",
    "selector",
    "name",
    "scopes",
    "status",
    "metadata",
    "created_at",
    "expires_at",
    "last_used_at",
    "rotated_from",
    "grace_until",
)


class SQLiteKeyBackend:
    """Persists API keys in a local SQLite database.

    The ``selector`` column is uniquely indexed so verification is a single
    indexed lookup followed by one bcrypt check.

    Args:
        path: SQLite database file path.
    """

    def __init__(self, path: str = "fastmcp-guard-keys.db") -> None:
        self._path = Path(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id            TEXT PRIMARY KEY,
                    token_hash    TEXT NOT NULL,
                    selector      TEXT NOT NULL,
                    name          TEXT NOT NULL,
                    scopes        TEXT NOT NULL,
                    status        TEXT NOT NULL,
                    metadata      TEXT NOT NULL,
                    created_at    TEXT NOT NULL,
                    expires_at    TEXT,
                    last_used_at  TEXT,
                    rotated_from  TEXT,
                    grace_until   TEXT
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_selector "
                "ON api_keys(selector)"
            )
            conn.commit()

    # -- serialization -------------------------------------------------------

    @staticmethod
    def _to_row(key: APIKey) -> dict:
        def iso(dt) -> str | None:
            return dt.isoformat() if dt else None

        status = key.status.value if hasattr(key.status, "value") else key.status
        return {
            "id": key.id,
            "token_hash": key.token_hash,
            "selector": key.selector,
            "name": key.name,
            "scopes": json.dumps(key.scopes),
            "status": status,
            "metadata": json.dumps(key.metadata),
            "created_at": iso(key.created_at),
            "expires_at": iso(key.expires_at),
            "last_used_at": iso(key.last_used_at),
            "rotated_from": key.rotated_from,
            "grace_until": iso(key.grace_until),
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> APIKey:
        return APIKey(
            id=row["id"],
            token=None,  # never persisted
            token_hash=row["token_hash"],
            selector=row["selector"],
            name=row["name"],
            scopes=json.loads(row["scopes"]),
            status=row["status"],
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            last_used_at=row["last_used_at"],
            rotated_from=row["rotated_from"],
            grace_until=row["grace_until"],
        )

    def _upsert(self, key: APIKey) -> None:
        row = self._to_row(key)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        assignments = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS if c != "id")
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO api_keys ({', '.join(_COLUMNS)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT(id) DO UPDATE SET {assignments}",
                [row[c] for c in _COLUMNS],
            )
            conn.commit()

    # -- KeyBackend protocol -------------------------------------------------

    def add(self, key: APIKey) -> None:
        self._upsert(key)

    def update(self, key: APIKey) -> None:
        self._upsert(key)

    def get_by_id(self, key_id: str) -> APIKey | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE id = ?", (key_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def get_by_selector(self, selector: str) -> APIKey | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE selector = ?", (selector,)
            ).fetchone()
        return self._from_row(row) if row else None

    def all(self) -> list[APIKey]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM api_keys ORDER BY created_at"
            ).fetchall()
        return [self._from_row(r) for r in rows]
