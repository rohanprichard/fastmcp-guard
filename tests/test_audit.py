"""Tests for audit logging."""

import json
import tempfile
from pathlib import Path

import pytest

from fastmcp_guard.audit.backends.file import FileBackend
from fastmcp_guard.audit.backends.sqlite import SQLiteAuditBackend
from fastmcp_guard.audit.log import AuditLog, AuditRecord


@pytest.mark.asyncio
async def test_file_backend_writes_jsonl():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name

    backend = FileBackend(path)
    record = AuditRecord(
        key_id="fmg_key_abc",
        key_name="alice",
        tool="get_data",
        scopes=["read:data"],
        duration_ms=42.0,
        status="ok",
    )
    await backend.write(record)

    lines = Path(path).read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["key_name"] == "alice"
    assert data["tool"] == "get_data"
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_file_backend_appends():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name

    backend = FileBackend(path)
    for i in range(3):
        await backend.write(AuditRecord(tool=f"tool_{i}", key_name="alice"))

    lines = Path(path).read_text().strip().split("\n")
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_sqlite_backend_write_and_query():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    backend = SQLiteAuditBackend(path)
    await backend.write(AuditRecord(key_name="alice", tool="get_data", status="ok"))
    await backend.write(AuditRecord(key_name="bob", tool="list_files", status="ok"))
    await backend.write(
        AuditRecord(key_name="alice", tool="delete_all", status="error")
    )

    all_records = await backend.query(limit=10)
    assert len(all_records) == 3

    alice_records = await backend.query(key_name="alice", limit=10)
    assert len(alice_records) == 2

    error_records = await backend.query(limit=10)
    errors = [r for r in error_records if r.status == "error"]
    assert len(errors) == 1
    assert errors[0].tool == "delete_all"


@pytest.mark.asyncio
async def test_audit_log_strips_inputs_when_disabled():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name

    audit = AuditLog(backend=FileBackend(path), log_inputs=False)
    record = AuditRecord(
        key_name="alice",
        tool="get_data",
        input_args={"query": "secret data"},
    )
    await audit.write(record)

    lines = Path(path).read_text().strip().split("\n")
    data = json.loads(lines[0])
    assert data["input_args"] is None


@pytest.mark.asyncio
async def test_audit_log_strips_outputs_when_disabled():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name

    audit = AuditLog(backend=FileBackend(path), log_outputs=False)
    record = AuditRecord(
        key_name="alice",
        tool="get_data",
        output_preview="sensitive result",
    )
    await audit.write(record)

    lines = Path(path).read_text().strip().split("\n")
    data = json.loads(lines[0])
    assert data["output_preview"] is None
