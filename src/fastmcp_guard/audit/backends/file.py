"""File (JSONL) audit backend."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp_guard.audit.log import AuditRecord


class FileBackend:
    """Append-only JSONL audit log backend.

    Each record is written as one JSON line, making the file easy to
    tail, rotate, and ingest into any log aggregator.

    Args:
        path: File path to write to. Created if it doesn't exist.
    """

    def __init__(self, path: str = "fastmcp-guard-audit.jsonl") -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()

    async def write(self, record: AuditRecord) -> None:
        line = json.dumps(record.to_dict()) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append, line)

    def _append(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)
