#!/usr/bin/env python3
"""
Full-featured FastMCP server with Guard configured for all features.

This server demonstrates the INTENDED configuration with all features enabled:
- Memory keystore ([BUG-001] sqlite won't work)
- Per-key and global rate limiting
- Dual audit logging (file JSONL + SQLite)
- IP policy (localhost only)
- Mix of sync and async tools
- One tool with @rate_limit decorator ([BUG-004] doesn't work)

Start: .venv/bin/python examples/walkthrough/server.py
Access: http://127.0.0.1:8000
"""

import asyncio
from datetime import datetime
from fastmcp import FastMCP
from fastmcp_guard import Guard, KeyStore, RateLimit, AuditLog, IPPolicy
from fastmcp_guard.rate import rate_limit


# ============================================================================
# SERVER SETUP
# ============================================================================

print("🚀 Initializing fastmcp-guard demonstration server...")
print()

# Initialize FastMCP
mcp = FastMCP("guard-demo-server")

# Configure Guard with ALL features enabled
print("🔧 Configuring Guard with all features:")
print()

# [BUG-001] Memory backend only (sqlite/postgres/redis don't exist)
print("   🔑 KeyStore: memory backend")
print("      ⚠️  [BUG-001] SQLite backend would crash")
keys = KeyStore(backend="memory")

# Rate limiting: per-key + global
print("   🚦 RateLimit: 100/minute per-key, 1000/minute global")
rate_limit_config = RateLimit(
    per_key="100/minute",
    global_limit="1000/minute",
    backend="memory"
)

# Audit logging: File (JSONL) backend
# [BUG-009] Uses blocking I/O, but still configured
print("   📋 AuditLog: file backend (JSONL)")
print("      ⚠️  [BUG-002] Won't write (Guard never calls it)")
print("      ⚠️  [BUG-009] Uses blocking I/O")
audit_file = AuditLog(
    backend="file",
    path="guard_demo_audit.jsonl",
    log_inputs=True,
    log_outputs=True
)

# Also configure SQLite audit backend for queryable logs
print("   📋 AuditLog: sqlite backend (queryable)")
print("      ⚠️  [BUG-002] Won't write (Guard never calls it)")
print("      ⚠️  [BUG-009] Uses blocking I/O")
audit_sqlite = AuditLog(
    backend="sqlite",
    path="guard_demo_audit.db",
    log_inputs=True,
    log_outputs=True
)

# IP policy: Allow only localhost
print("   🌐 IPPolicy: allow localhost only")
print("      ⚠️  [BUG-003] Never enforced (Guard ignores it)")
ip_policy = IPPolicy(
    allow=["127.0.0.0/8", "::1"],  # IPv4 and IPv6 localhost
)

print()

# Install Guard with all configured features
# NOTE: We can only use ONE audit backend at a time, using file for this demo
guard = Guard(
    mcp,
    keys=keys,
    rate_limit=rate_limit_config,
    audit=audit_file,  # Using file backend (could use audit_sqlite instead)
    ip=ip_policy,
)

print("✅ Guard installed on FastMCP server")
print()


# ============================================================================
# CREATE DEMO API KEYS
# ============================================================================

print("🔑 Creating demonstration API keys...")
print()

# Key 1: Full access
key_admin = guard.keys.create(
    name="admin-key",
    scopes=["read:*", "write:*", "admin:*"],
    expires_in_days=30,
    metadata={"role": "admin", "user": "demo-admin"}
)
print(f"   Admin Key: {key_admin.token}")
print(f"   ID: {key_admin.id}")
print(f"   Scopes: {key_admin.scopes}")
print()

# Key 2: Read-only
key_readonly = guard.keys.create(
    name="readonly-key",
    scopes=["read:data"],
    expires_in_days=7,
    metadata={"role": "viewer", "user": "demo-viewer"}
)
print(f"   Read-Only Key: {key_readonly.token}")
print(f"   ID: {key_readonly.id}")
print(f"   Scopes: {key_readonly.scopes}")
print()

# Key 3: Test rotation
key_rotate = guard.keys.create(
    name="rotate-test-key",
    scopes=["read:data", "write:data"],
    metadata={"purpose": "rotation-demo"}
)
old_token = key_rotate.token
print(f"   Rotation Test Key (original): {old_token}")

# Rotate with 1-hour grace period
# [BUG-005] Grace period never expires (no background task)
key_rotated = guard.keys.rotate(key_rotate.id, grace_period_hours=1)
print(f"   Rotation Test Key (new): {key_rotated.token}")
print(f"   ⚠️  [BUG-005] Old token stays valid forever (grace never expires)")
print()


# ============================================================================
# TOOLS - Mix of sync and async
# ============================================================================

print("🛠️  Registering tools...")
print()

@mcp.tool()
async def get_server_time() -> str:
    """
    ASYNC: Get the current server time.

    This is a simple async tool that returns the current UTC timestamp.
    """
    await asyncio.sleep(0.001)  # Simulate async work
    return datetime.utcnow().isoformat()


@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """
    SYNC: Add two numbers together.

    This is a synchronous tool demonstrating that Guard works with
    both sync and async tools.
    """
    return a + b


@mcp.tool()
async def fetch_data(resource_id: str) -> dict:
    """
    ASYNC: Fetch data for a given resource.

    Simulates an async database or API call.
    """
    await asyncio.sleep(0.05)  # Simulate I/O
    return {
        "id": resource_id,
        "status": "active",
        "data": f"Resource data for {resource_id}",
        "timestamp": datetime.utcnow().isoformat()
    }


@mcp.tool()
def calculate_stats(values: list[float]) -> dict:
    """
    SYNC: Calculate statistics for a list of values.

    Returns mean, min, max, and count.
    """
    if not values:
        return {"error": "No values provided"}

    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "sum": sum(values)
    }


# [BUG-004] This decorator sets metadata but Guard never reads it
# [BUG-008] This would also break if the function was sync (await on non-coroutine)
@mcp.tool()
@rate_limit("10/minute")
async def expensive_operation(query: str) -> str:
    """
    ASYNC + @rate_limit: Expensive operation with tighter rate limit.

    This tool is decorated with @rate_limit("10/minute") which SHOULD
    enforce a tighter limit than the global 100/minute per-key limit.

    [BUG-004] The decorator is a no-op — metadata is set but never checked.
    Only the global per-key rate limit (100/minute) applies.
    """
    await asyncio.sleep(0.1)  # Simulate expensive work
    return f"Expensive result for: {query}"


@mcp.tool()
async def simulate_long_task(duration_seconds: float) -> str:
    """
    ASYNC: Simulate a long-running task.

    Useful for testing concurrent request handling and rate limits.
    """
    if duration_seconds > 10:
        return "Error: Duration too long (max 10s)"

    await asyncio.sleep(duration_seconds)
    return f"Task completed after {duration_seconds}s"


print(f"   ✓ Registered {len(mcp._tools)} tools")
print()


# ============================================================================
# STARTUP
# ============================================================================

def main():
    """Start the server."""
    print("="*60)
    print("  FASTMCP-GUARD DEMO SERVER")
    print("="*60)
    print()
    print("🌐 Server: http://127.0.0.1:8000")
    print()
    print("📊 Features enabled:")
    print("   ✓ API key authentication (memory backend)")
    print("   ✓ Per-key rate limiting (100/minute)")
    print("   ✓ Global rate limiting (1000/minute)")
    print("   ✗ Audit logging (configured but broken) [BUG-002]")
    print("   ✗ IP policy (configured but not enforced) [BUG-003]")
    print("   ✗ @rate_limit decorator (no-op) [BUG-004]")
    print()
    print("🔑 API Keys created:")
    print(f"   Admin: {key_admin.token}")
    print(f"   Read-only: {key_readonly.token}")
    print(f"   Rotated: {key_rotated.token} (old also works) [BUG-005]")
    print()
    print("🛠️  Available tools:")
    print("   - get_server_time() → async")
    print("   - add_numbers(a, b) → sync")
    print("   - fetch_data(resource_id) → async")
    print("   - calculate_stats(values) → sync")
    print("   - expensive_operation(query) → async + @rate_limit [BROKEN]")
    print("   - simulate_long_task(duration_seconds) → async")
    print()
    print("⚠️  Known Issues:")
    print("   [BUG-001] SQLite backend crashes — using memory only")
    print("   [BUG-002] Audit logs never written (Guard doesn't call write)")
    print("   [BUG-003] IP policy not enforced (any IP can connect)")
    print("   [BUG-004] @rate_limit decorator is ignored")
    print("   [BUG-005] Grace periods never expire (old tokens work forever)")
    print("   [BUG-007] Rate limiter has race condition under load")
    print("   [BUG-009] Audit backends use blocking I/O")
    print()
    print("📖 See BUGS.md for detailed bug reports")
    print()
    print("Press Ctrl+C to stop")
    print("="*60)
    print()

    # Start the server
    # Using streamable-http transport on port 8000
    mcp.run(transport="streamable-http", port=8000)


if __name__ == "__main__":
    main()
