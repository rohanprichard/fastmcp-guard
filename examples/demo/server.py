"""fastmcp-guard demo server.

Runs a FastMCP server over HTTP, protected by fastmcp-guard:

- API-key authentication (Bearer token)
- Per-key rate limiting + a tighter per-tool limit on one expensive tool
- Audit logging to a JSONL file
- IP policy (localhost is allowed)

On startup it provisions a demo API key and writes the token to
``.demo_token`` next to this file, so ``client.py`` can pick it up. In a real
deployment you'd issue keys with the CLI or the programmatic API and hand the
token to the caller out of band — never write tokens to disk like this.

Run:

    python examples/demo/server.py

Then, in another terminal:

    python examples/demo/client.py
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from fastmcp_guard import AuditLog, Guard, IPPolicy, KeyStore, RateLimit
from fastmcp_guard.rate import rate_limit

HERE = Path(__file__).parent
TOKEN_FILE = HERE / ".demo_token"
AUDIT_FILE = HERE / "audit.jsonl"

HOST = "127.0.0.1"
PORT = 8000

# --- Define the MCP server and its tools ------------------------------------

mcp = FastMCP("demo-server")


@mcp.tool
def get_weather(city: str) -> str:
    """A cheap, frequently-called tool."""
    return f"It's sunny in {city}, 22°C."


@mcp.tool
def echo(message: str) -> str:
    return message


@mcp.tool
@rate_limit("3/minute")  # tighter per-tool limit on top of the per-key limit
def expensive_report(topic: str) -> str:
    """A costly tool we want to throttle harder than everything else."""
    return f"Generated an expensive report on: {topic}"


# --- Wrap it with fastmcp-guard ---------------------------------------------

guard = Guard(
    mcp,
    keys=KeyStore(backend="memory"),           # dev demo; use sqlite in prod
    rate_limit=RateLimit(per_key="20/minute"), # overall per-key ceiling
    audit=AuditLog(backend="file", path=str(AUDIT_FILE)),
    ip=IPPolicy(allow=["127.0.0.0/8", "::1"]), # only localhost may connect
)


def main() -> None:
    AUDIT_FILE.unlink(missing_ok=True)  # start each demo run with a clean log

    # Provision a key for the demo client and hand off the token via a file.
    key = guard.keys.create(name="demo-client", scopes=["read:data"])
    TOKEN_FILE.write_text(key.token or "")

    print("=" * 60)
    print("fastmcp-guard demo server")
    print("=" * 60)
    print(f"  URL:        http://{HOST}:{PORT}/mcp/")
    print(f"  Key id:     {key.id}")
    print(f"  Token:      {key.token}")
    print(f"  Token file: {TOKEN_FILE}")
    print(f"  Audit log:  {AUDIT_FILE}")
    print("\nNow run:  python examples/demo/client.py")
    print("Press Ctrl+C to stop.\n")

    mcp.run(transport="http", host=HOST, port=PORT, show_banner=False)


if __name__ == "__main__":
    main()
