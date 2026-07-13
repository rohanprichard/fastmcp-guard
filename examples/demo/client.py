"""fastmcp-guard demo client.

Connects to the demo server (start it first with ``python examples/demo/server.py``)
and walks through what fastmcp-guard enforces:

1. A valid API key authenticates and can call tools.
2. An invalid/missing key is rejected by the auth layer.
3. A per-tool rate limit trips after a few calls.
4. Every call is recorded in the server's audit log.

Run:

    python examples/demo/client.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastmcp import Client

HERE = Path(__file__).parent
TOKEN_FILE = HERE / ".demo_token"
AUDIT_FILE = HERE / "audit.jsonl"
URL = "http://127.0.0.1:8000/mcp/"


def _rule(title: str) -> None:
    print(f"\n{'─' * 60}\n{title}\n{'─' * 60}")


async def main() -> None:
    if not TOKEN_FILE.exists():
        raise SystemExit(
            "No token found. Start the server first:\n"
            "    python examples/demo/server.py"
        )
    token = TOKEN_FILE.read_text().strip()

    # 1. Valid token -------------------------------------------------------
    _rule("1. Valid API key — authenticated calls succeed")
    async with Client(URL, auth=token) as client:
        tools = await client.list_tools()
        print("   tools available:", [t.name for t in tools])
        weather = await client.call_tool("get_weather", {"city": "Lisbon"})
        print("   get_weather ->", weather.data)
        echoed = await client.call_tool("echo", {"message": "hello guard"})
        print("   echo        ->", echoed.data)

    # 2. Invalid token -----------------------------------------------------
    _rule("2. Invalid API key — rejected by the auth layer")
    try:
        async with Client(URL, auth="fmg_sk_not.a_real_token") as client:
            await client.call_tool("get_weather", {"city": "Nowhere"})
        print("   ERROR: call unexpectedly succeeded!")
    except Exception as exc:  # noqa: BLE001 - demo
        print(f"   rejected as expected: {type(exc).__name__}")

    # 3. Per-tool rate limit ----------------------------------------------
    _rule("3. Per-tool rate limit — expensive_report is capped at 3/minute")
    async with Client(URL, auth=token) as client:
        for i in range(1, 6):
            try:
                result = await client.call_tool("expensive_report", {"topic": f"q{i}"})
                print(f"   call {i}: OK    -> {result.data}")
            except Exception as exc:  # noqa: BLE001 - demo
                print(f"   call {i}: BLOCKED ({type(exc).__name__}) — rate limited")

    # 4. Audit log ---------------------------------------------------------
    _rule("4. Audit log — every call was recorded (server side)")
    if AUDIT_FILE.exists():
        records = [json.loads(line) for line in AUDIT_FILE.read_text().splitlines()]
        print(f"   {len(records)} records written to {AUDIT_FILE.name}:")
        for r in records:
            print(
                f"   - {r['tool']:<18} key={r['key_name'] or '?':<12} "
                f"status={r['status']:<12} ip={r['client_ip']}"
            )
    else:
        print("   (run the client from the same machine as the server to see the log)")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
