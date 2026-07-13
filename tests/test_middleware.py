"""End-to-end tests for GuardMiddleware via an in-memory FastMCP client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import TokenVerifier

from fastmcp_guard import AuditLog, Guard, IPPolicy, RateLimit
from fastmcp_guard.middleware import GuardMiddleware
from fastmcp_guard.rate import rate_limit


def _build_server(**guard_kwargs) -> FastMCP:
    mcp = FastMCP("test")

    @mcp.tool
    def get_data(query: str) -> str:
        return f"Results for: {query}"

    @mcp.tool
    @rate_limit("2/minute")
    def expensive(x: int) -> int:
        return x * 2

    @mcp.tool
    def boom() -> str:
        raise ValueError("kaboom")

    Guard(mcp, **guard_kwargs)
    return mcp


async def test_audit_records_written(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    mcp = _build_server(audit=AuditLog(backend="file", path=str(audit_path)))

    async with Client(mcp) as client:
        result = await client.call_tool("get_data", {"query": "hi"})
        assert result.data == "Results for: hi"

    records = [json.loads(x) for x in audit_path.read_text().splitlines()]
    assert len(records) == 1
    rec = records[0]
    assert rec["tool"] == "get_data"
    assert rec["status"] == "ok"
    assert rec["input_args"] == {"query": "hi"}
    assert rec["duration_ms"] >= 0


async def test_audit_captures_tool_error(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    mcp = _build_server(audit=AuditLog(backend="file", path=str(audit_path)))

    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("boom", {})

    records = [json.loads(x) for x in audit_path.read_text().splitlines()]
    assert records[-1]["tool"] == "boom"
    assert records[-1]["status"] == "error"


async def test_per_tool_rate_limit_trips(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    mcp = _build_server(audit=AuditLog(backend="file", path=str(audit_path)))

    async with Client(mcp) as client:
        await client.call_tool("expensive", {"x": 1})
        await client.call_tool("expensive", {"x": 2})
        with pytest.raises(ToolError):
            await client.call_tool("expensive", {"x": 3})

    statuses = [json.loads(x)["status"] for x in audit_path.read_text().splitlines()]
    assert statuses.count("rate_limited") == 1


async def test_per_key_rate_limit_trips() -> None:
    mcp = _build_server(rate_limit=RateLimit(per_key="2/minute"))

    async with Client(mcp) as client:
        await client.call_tool("get_data", {"query": "a"})
        await client.call_tool("get_data", {"query": "b"})
        with pytest.raises(ToolError):
            await client.call_tool("get_data", {"query": "c"})


async def test_audit_log_inputs_disabled(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    mcp = _build_server(
        audit=AuditLog(backend="file", path=str(audit_path), log_inputs=False)
    )
    async with Client(mcp) as client:
        await client.call_tool("get_data", {"query": "secret"})

    rec = json.loads(audit_path.read_text().splitlines()[0])
    assert rec["input_args"] is None


# -- IP policy enforcement (unit-level; client IP needs an HTTP transport) ----


class _Msg:
    name = "get_data"
    arguments: dict = {}


class _Ctx:
    message = _Msg()
    fastmcp_context = None  # forces _tool_limit to no-op


async def _call_next(_ctx):
    return "ok"


async def test_ip_policy_blocks_disallowed(monkeypatch) -> None:
    mw = GuardMiddleware(ip=IPPolicy(allow=["10.0.0.0/8"]))
    monkeypatch.setattr(GuardMiddleware, "_client_ip", staticmethod(lambda: "8.8.8.8"))
    with pytest.raises(ToolError):
        await mw.on_call_tool(_Ctx(), _call_next)


async def test_ip_policy_allows_permitted(monkeypatch) -> None:
    mw = GuardMiddleware(ip=IPPolicy(allow=["10.0.0.0/8"]))
    monkeypatch.setattr(GuardMiddleware, "_client_ip", staticmethod(lambda: "10.0.0.5"))
    assert await mw.on_call_tool(_Ctx(), _call_next) == "ok"


# -- auth composition (compose with external OAuth/JWT) -----------------------


class _ExternalVerifier(TokenVerifier):
    async def verify_token(self, token):  # noqa: ANN001, ANN201
        return None


def test_installs_key_verifier_when_no_auth() -> None:
    from fastmcp_guard.keys.verifier import KeyStoreVerifier

    mcp = FastMCP("x")
    Guard(mcp)
    assert isinstance(mcp.auth, KeyStoreVerifier)


def test_preserves_existing_auth_by_default() -> None:
    mcp = FastMCP("x", auth=_ExternalVerifier())
    Guard(mcp)  # manage_auth=None -> don't clobber existing auth
    assert isinstance(mcp.auth, _ExternalVerifier)


def test_manage_auth_false_never_touches_auth() -> None:
    mcp = FastMCP("x", auth=_ExternalVerifier())
    Guard(mcp, manage_auth=False)
    assert isinstance(mcp.auth, _ExternalVerifier)


def test_manage_auth_true_overrides() -> None:
    from fastmcp_guard.keys.verifier import KeyStoreVerifier

    mcp = FastMCP("x", auth=_ExternalVerifier())
    Guard(mcp, manage_auth=True)
    assert isinstance(mcp.auth, KeyStoreVerifier)
