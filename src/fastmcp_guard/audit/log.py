"""Audit logging — structured records of every tool call."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, runtime_checkable


@runtime_checkable
class AuditBackend(Protocol):
    """Minimal interface an audit backend must implement."""

    async def write(self, record: AuditRecord) -> None:
        """Persist one audit record."""
        ...


@dataclass
class AuditRecord:
    """A single audit log entry for one tool call.

    Attributes:
        ts: UTC timestamp of the call.
        key_id: ID of the API key that made the call.
        key_name: Human-readable key name.
        tool: Name of the tool called.
        scopes: Scopes the key had at call time.
        duration_ms: Wall-clock time of the tool execution.
        status: ``ok``, ``error``, ``rate_limited``, or ``unauthorized``.
        error: Error message if status is ``error``.
        input_args: Tool input arguments (omitted if ``log_inputs=False``).
        output_preview: First 200 chars of output (omitted if ``log_outputs=False``).
        client_ip: IP address of the caller (if available).
        metadata: Additional key metadata at call time.
    """

    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    key_id: str = ""
    key_name: str = ""
    tool: str = ""
    scopes: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    status: Literal["ok", "error", "rate_limited", "unauthorized"] = "ok"
    error: str | None = None
    input_args: dict[str, Any] | None = None
    output_preview: str | None = None
    client_ip: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "key_id": self.key_id,
            "key_name": self.key_name,
            "tool": self.tool,
            "scopes": self.scopes,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "error": self.error,
            "input_args": self.input_args,
            "output_preview": self.output_preview,
            "client_ip": self.client_ip,
            "metadata": self.metadata,
        }


class AuditLog:
    """Writes structured audit records for every tool call.

    Args:
        backend: Where to write records. Accepts a backend instance or a
            shorthand string: ``"file"``, ``"sqlite"``, ``"http"``, ``"otel"``.
        path: File/DB path (for file and sqlite backends).
        url: Endpoint URL (for http backend).
        log_inputs: If False, input arguments are omitted from records.
            Default True. Set False when args may contain PII.
        log_outputs: If False, output previews are omitted. Default True.

    Example:
        ```python
        from fastmcp_guard.audit import AuditLog, FileBackend

        audit = AuditLog(
            backend=FileBackend("audit.jsonl"),
            log_inputs=False,  # Don't log PII
        )
        ```
    """

    def __init__(
        self,
        backend: Any = None,
        path: str | None = None,
        url: str | None = None,
        log_inputs: bool = True,
        log_outputs: bool = True,
    ) -> None:
        self._log_inputs = log_inputs
        self._log_outputs = log_outputs
        self._backend: AuditBackend

        if backend is None or backend == "file":
            from fastmcp_guard.audit.backends.file import FileBackend
            self._backend = FileBackend(path or "fastmcp-guard-audit.jsonl")
        elif backend == "sqlite":
            from fastmcp_guard.audit.backends.sqlite import SQLiteAuditBackend
            self._backend = SQLiteAuditBackend(path or "fastmcp-guard-audit.db")
        elif backend == "http":
            from fastmcp_guard.audit.backends.http import HttpBackend
            if not url:
                raise ValueError("url required for http audit backend")
            self._backend = HttpBackend(url)
        elif backend == "otel":
            from fastmcp_guard.audit.backends.otel import OTelBackend
            self._backend = OTelBackend()
        else:
            self._backend = backend  # assume it's a backend instance

    async def write(self, record: AuditRecord) -> None:
        """Write an audit record to the configured backend."""
        if not self._log_inputs:
            record.input_args = None
        if not self._log_outputs:
            record.output_preview = None
        await self._backend.write(record)

    async def query(
        self,
        key_id: str | None = None,
        key_name: str | None = None,
        tool: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """Query audit records. Only supported by sqlite backend."""
        query_fn = getattr(self._backend, "query", None)
        if query_fn is not None:
            records: list[AuditRecord] = await query_fn(
                key_id=key_id,
                key_name=key_name,
                tool=tool,
                since=since,
                limit=limit,
            )
            return records
        raise NotImplementedError(
            f"The {type(self._backend).__name__} backend does not support querying. "
            "Use the sqlite backend for queryable audit logs."
        )
