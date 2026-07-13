"""SQLite queryable audit backend."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp_guard.audit.log import AuditRecord


class SQLiteAuditBackend:
    """Queryable SQLite audit log backend.

    Stores records in a local SQLite database. Supports querying by
    key, tool name, and time range via ``AuditLog.query()``.

    Args:
        path: SQLite database file path.
    """

    def __init__(self, path: str = "fastmcp-guard-audit.db") -> None:
        self._path = Path(path)
        self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    key_id TEXT,
                    key_name TEXT,
                    tool TEXT,
                    scopes TEXT,
                    duration_ms REAL,
                    status TEXT,
                    error TEXT,
                    input_args TEXT,
                    output_preview TEXT,
                    client_ip TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON audit_log(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_key_id ON audit_log(key_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool ON audit_log(tool)")
            conn.commit()

    async def write(self, record: AuditRecord) -> None:
        await asyncio.to_thread(self._write_sync, record)

    def _write_sync(self, record: AuditRecord) -> None:
        d = record.to_dict()
        with closing(sqlite3.connect(self._path)) as conn:
            conn.execute(
                """
                INSERT INTO audit_log
                    (ts, key_id, key_name, tool, scopes, duration_ms,
                     status, error, input_args, output_preview, client_ip, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d["ts"], d["key_id"], d["key_name"], d["tool"],
                    json.dumps(d["scopes"]), d["duration_ms"], d["status"],
                    d["error"], json.dumps(d["input_args"]),
                    d["output_preview"], d["client_ip"], json.dumps(d["metadata"]),
                ),
            )
            conn.commit()

    async def query(
        self,
        key_id: str | None = None,
        key_name: str | None = None,
        tool: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        return await asyncio.to_thread(
            self._query_sync, key_id, key_name, tool, since, limit
        )

    def _query_sync(
        self,
        key_id: str | None = None,
        key_name: str | None = None,
        tool: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        from fastmcp_guard.audit.log import AuditRecord

        conditions: list[str] = []
        params: list[Any] = []
        if key_id:
            conditions.append("key_id = ?")
            params.append(key_id)
        if key_name:
            conditions.append("key_name = ?")
            params.append(key_name)
        if tool:
            conditions.append("tool = ?")
            params.append(tool)
        if since:
            conditions.append("ts >= ?")
            params.append(since.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM audit_log {where} ORDER BY ts DESC LIMIT ?", params
            ).fetchall()

        records = []
        for row in rows:
            records.append(AuditRecord(
                ts=row["ts"],
                key_id=row["key_id"] or "",
                key_name=row["key_name"] or "",
                tool=row["tool"] or "",
                scopes=json.loads(row["scopes"] or "[]"),
                duration_ms=row["duration_ms"] or 0.0,
                status=row["status"] or "ok",
                error=row["error"],
                input_args=json.loads(row["input_args"]) if row["input_args"] else None,
                output_preview=row["output_preview"],
                client_ip=row["client_ip"],
                metadata=json.loads(row["metadata"] or "{}"),
            ))
        return records
