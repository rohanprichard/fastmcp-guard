#!/usr/bin/env python3
"""
POC server demonstrating fastmcp-guard with FastMCP over HTTP.

This server shows:
- API key authentication
- Rate limiting (per-key)
- Multiple tools (sync and async)
- What works and what doesn't

Start: .venv/bin/python examples/walkthrough/poc_server.py
Then run poc_client.py to interact with it.
"""

import asyncio
from fastmcp import FastMCP
from fastmcp_guard import Guard, KeyStore, RateLimit, AuditLog, IPPolicy

# Initialize FastMCP server
mcp = FastMCP("fastmcp-guard-poc")

# Initialize Guard with all features
# [BUG-001] Using memory backend because sqlite doesn't exist
print("🔧 Initializing Guard...")
print("   ⚠️  [BUG-001] Using memory backend (sqlite crashes)")

guard = Guard(
    mcp,
    keys=KeyStore(backend="memory"),
    rate_limit=RateLimit(per_key="5/minute", backend="memory"),
    # [BUG-002] Audit logging is configured but won't write (Guard never calls it)
    audit=AuditLog(backend="file", path="poc_audit.jsonl"),
    # [BUG-003] IP policy is configured but never enforced
    ip=IPPolicy(allow=["127.0.0.0/8", "::1"]),  # Only allow localhost
)

print("   ✓ Guard initialized")
print()

# Create a demo API key for testing
print("🔑 Creating demo API key...")
demo_key = guard.keys.create(
    name="poc-demo-key",
    scopes=["read:data", "write:data"],
    metadata={"purpose": "POC testing"}
)
demo_token = demo_key.token
print(f"   Token: {demo_token}")
print(f"   Key ID: {demo_key.id}")
print()
print("   💾 Save this token for poc_client.py!")
print()

# Create a second key for revocation demo
revoke_key = guard.keys.create(
    name="revoke-demo-key",
    scopes=["read:data"],
)
revoke_token = revoke_key.token
print(f"🔑 Created revoke-demo key: {revoke_token}")
print(f"   Key ID: {revoke_key.id}")
print()

# Immediately revoke it for testing
guard.keys.revoke(revoke_key.id)
print(f"   ✓ Revoked for testing")
print()


# ============================================================================
# TOOLS
# ============================================================================

@mcp.tool()
async def get_data(query: str) -> str:
    """
    Async tool: Retrieve data based on a query.

    This demonstrates an async tool with Guard authentication.
    """
    await asyncio.sleep(0.01)  # Simulate async work
    return f"Data for query '{query}': [result-async-{len(query)}]"


@mcp.tool()
def calculate(x: int, y: int) -> int:
    """
    Sync tool: Perform a calculation.

    This demonstrates a synchronous tool with Guard authentication.
    """
    return x + y


@mcp.tool()
async def slow_operation(seconds: float) -> str:
    """
    Async tool: Simulate a slow operation.

    Useful for testing rate limiting and concurrent requests.
    """
    await asyncio.sleep(seconds)
    return f"Completed after {seconds}s"


# [BUG-004] This decorator does nothing (metadata is set but never read)
from fastmcp_guard.rate import rate_limit

@mcp.tool()
@rate_limit("2/minute")
async def expensive_analysis(data: str) -> str:
    """
    Tool with per-tool rate limit (decorator).

    [BUG-004] The @rate_limit decorator is a no-op — it sets metadata
    but Guard never reads it. Only the global per-key limit applies.
    """
    await asyncio.sleep(0.05)
    return f"Analysis result for: {data[:50]}"


# ============================================================================
# SERVER STARTUP
# ============================================================================

def main():
    """Start the server."""
    print("="*60)
    print("  POC SERVER READY")
    print("="*60)
    print()
    print(f"📡 Starting server on http://127.0.0.1:8765")
    print()
    print("Available tools:")
    print("  - get_data(query: str) → async")
    print("  - calculate(x: int, y: int) → sync")
    print("  - slow_operation(seconds: float) → async")
    print("  - expensive_analysis(data: str) → async + @rate_limit (broken)")
    print()
    print("Rate limits:")
    print("  - Per-key: 5 requests/minute")
    print("  - Per-tool (@rate_limit): NOT ENFORCED [BUG-004]")
    print()
    print("Known issues:")
    print("  ⚠️  [BUG-002] Audit logging won't write (Guard never calls it)")
    print("  ⚠️  [BUG-003] IP policy not enforced (any IP can connect)")
    print("  ⚠️  [BUG-004] @rate_limit decorator is a no-op")
    print()
    print("To test:")
    print("  .venv/bin/python examples/walkthrough/poc_client.py")
    print()
    print("Press Ctrl+C to stop")
    print("="*60)
    print()

    # Start server on port 8765
    # Using streamable-http transport for HTTP access
    mcp.run(transport="streamable-http", port=8765)


if __name__ == "__main__":
    main()
