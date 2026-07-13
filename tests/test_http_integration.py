"""Real-transport integration tests: authentication, audit identity, IP policy.

These boot a FastMCP server over HTTP on a loopback port so the full request
path (Bearer auth -> KeyStoreVerifier -> GuardMiddleware) is exercised. If a
port cannot be bound (restricted CI sandbox), the module is skipped.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

from fastmcp_guard import AuditLog, Guard, IPPolicy, KeyStore


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(port: int, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _serve(mcp: FastMCP, port: int) -> None:
    thread = threading.Thread(
        target=lambda: mcp.run(
            transport="http", host="127.0.0.1", port=port, show_banner=False
        ),
        daemon=True,
    )
    thread.start()
    if not _wait_port(port):
        pytest.skip("could not bind loopback HTTP server in this environment")


async def test_auth_audit_and_ip_over_http(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"

    mcp = FastMCP("http-demo")

    @mcp.tool
    def get_data(query: str) -> str:
        return f"Results for: {query}"

    guard = Guard(
        mcp,
        keys=KeyStore(backend="memory"),
        audit=AuditLog(backend="file", path=str(audit_path)),
    )
    key = guard.keys.create(name="alice", scopes=["read:data"])

    port = _free_port()
    _serve(mcp, port)
    url = f"http://127.0.0.1:{port}/mcp/"

    # Valid token authenticates and runs.
    async with Client(url, auth=key.token) as client:
        result = await client.call_tool("get_data", {"query": "hi"})
        assert result.data == "Results for: hi"

    # Invalid and missing tokens are rejected by the auth layer.
    for bad in ("fmg_sk_bogus.nope", None):
        with pytest.raises(Exception):  # noqa: B017,PT011 - transport 401
            async with Client(url, auth=bad) as client:
                await client.call_tool("get_data", {"query": "x"})

    time.sleep(0.3)  # let the async audit write land
    records = [json.loads(x) for x in audit_path.read_text().splitlines()]
    ok = [r for r in records if r["status"] == "ok"]
    assert ok, "no successful audit record written"
    assert ok[0]["key_name"] == "alice"
    assert ok[0]["client_ip"] in ("127.0.0.1", "::1")


async def test_ip_policy_blocks_over_http() -> None:
    mcp = FastMCP("ip-demo")

    @mcp.tool
    def ping() -> str:
        return "pong"

    guard = Guard(
        mcp,
        keys=KeyStore(backend="memory"),
        ip=IPPolicy(deny=["127.0.0.1", "::1"]),
    )
    key = guard.keys.create(name="bob")

    port = _free_port()
    _serve(mcp, port)
    url = f"http://127.0.0.1:{port}/mcp/"

    with pytest.raises(Exception):  # noqa: B017 - ToolError: IP denied
        async with Client(url, auth=key.token) as client:
            await client.call_tool("ping", {})
