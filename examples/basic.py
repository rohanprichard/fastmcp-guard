"""Basic example: API key auth with rate limiting and audit logging."""

from fastmcp import FastMCP
from fastmcp_guard import Guard
from fastmcp_guard.keys import KeyStore
from fastmcp_guard.rate import RateLimit
from fastmcp_guard.audit import AuditLog

mcp = FastMCP("my-guarded-server")

guard = Guard(
    mcp,
    keys=KeyStore(backend="sqlite", path="keys.db"),
    rate_limit=RateLimit(per_key="100/minute", global_limit="1000/minute"),
    audit=AuditLog(backend="sqlite", path="audit.db"),
)

# Provision a key on startup (or use the CLI)
startup_key = guard.keys.create(name="dev-key", scopes=["read:data", "write:data"])
print(f"Dev key: {startup_key.token}")


@mcp.tool
def get_data(query: str) -> str:
    """Retrieve data matching the query."""
    return f"Results for: {query}"


@mcp.tool
def write_data(key: str, value: str) -> dict:
    """Store a key-value pair."""
    return {"stored": True, "key": key}


if __name__ == "__main__":
    mcp.run()
