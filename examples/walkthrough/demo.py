#!/usr/bin/env python3
"""
Standalone demo of all fastmcp-guard components.

This script exercises each component individually (no HTTP server needed)
and demonstrates both working features and known bugs.

Run: .venv/bin/python examples/walkthrough/demo.py
"""

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastmcp_guard import KeyStore, RateLimit, AuditLog, IPPolicy
from fastmcp_guard.audit.log import AuditRecord


def section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


# ============================================================================
# 1. KEY LIFECYCLE DEMO
# ============================================================================


def demo_key_lifecycle():
    """Demonstrate the complete key lifecycle: create → verify → rotate → revoke."""
    section("1. KEY LIFECYCLE")

    # Initialize in-memory key store
    # [BUG-001] We use memory backend because sqlite/postgres/redis don't exist
    print("🔑 Creating in-memory KeyStore")
    print("   ⚠️  [BUG-001] SQLite backend crashes — only memory backend works\n")
    store = KeyStore(backend="memory")

    # Create a new API key
    print("✅ Creating new API key...")
    key = store.create(
        name="demo-key",
        scopes=["read:data", "write:data"],
        expires_in_days=30,
        metadata={"user": "alice", "env": "demo"}
    )
    print(f"   Key ID: {key.id}")
    print(f"   Token: {key.token[:20]}... (only shown once!)")
    print(f"   Scopes: {key.scopes}")
    print(f"   Status: {key.status}")
    print(f"   Created: {key.created_at}\n")

    # Save the token for later use
    token = key.token

    # Verify the token works
    print("✅ Verifying token...")
    verified = store.verify(token)
    assert verified is not None, "Token verification failed!"
    print(f"   ✓ Token valid for key: {verified.name}")
    print(f"   ✓ Scopes: {verified.scopes}")
    print(f"   ✓ Last used: {verified.last_used_at}\n")

    # List all keys (token NOT included in listing)
    print("✅ Listing all keys...")
    all_keys = store.list()
    print(f"   Total keys: {len(all_keys)}")
    for k in all_keys:
        print(f"   - {k.name}: {k.id} ({k.status})")
        assert k.token is None, "Token should not appear in list()"
    print()

    # Rotate the key (new token, old stays valid during grace period)
    print("✅ Rotating key with 24-hour grace period...")
    new_key = store.rotate(key.id, grace_period_hours=24)
    new_token = new_key.token
    print(f"   New key ID: {new_key.id}")
    print(f"   New token: {new_token[:20]}...")
    print(f"   Old key status: ROTATING\n")

    # Both tokens should work during grace period
    print("✅ Testing grace period (both tokens should work)...")
    old_verified = store.verify(token)
    new_verified = store.verify(new_token)
    print(f"   Old token: {'✓ VALID' if old_verified else '✗ INVALID'}")
    print(f"   New token: {'✓ VALID' if new_verified else '✗ INVALID'}")
    print()

    # [BUG-005] Grace periods never expire automatically
    print("⚠️  [BUG-005] Grace period never expires!")
    print("   Old tokens stay valid forever (no background task)\n")

    # Revoke a key
    print("✅ Revoking the new key...")
    store.revoke(new_key.id)
    print(f"   Key {new_key.id} revoked\n")

    # Verify revoked key fails
    print("✅ Verifying revoked token fails...")
    revoked_check = store.verify(new_token)
    assert revoked_check is None, "Revoked token should not verify!"
    print("   ✓ Revoked token correctly rejected\n")


# ============================================================================
# 2. RATE LIMITING DEMO
# ============================================================================


async def demo_rate_limiting():
    """Demonstrate rate limiting with sliding window algorithm."""
    section("2. RATE LIMITING")

    print("🚦 Creating RateLimit with 5 requests per minute per key\n")
    rl = RateLimit(
        per_key="5/minute",
        global_limit="10/minute",
        backend="memory"
    )

    test_key_id = "test_key_123"

    # Test normal usage (within limit)
    print("✅ Testing normal usage (5 requests, all allowed)...")
    for i in range(5):
        allowed = await rl.check(test_key_id)
        print(f"   Request {i+1}: {'✓ ALLOWED' if allowed else '✗ BLOCKED'}")
        assert allowed, f"Request {i+1} should be allowed"
    print()

    # Test rate limit enforcement (6th request should fail)
    print("✅ Testing rate limit enforcement (6th request should fail)...")
    allowed = await rl.check(test_key_id)
    print(f"   Request 6: {'✓ ALLOWED' if allowed else '✗ BLOCKED (rate limited)'}")
    assert not allowed, "6th request should be rate-limited"
    print()

    # Check status
    print("✅ Checking rate limit status...")
    status = rl.status(test_key_id)
    print(f"   Per-key limit: {status['per_key']['used']}/{status['per_key']['limit']}")
    print(f"   Remaining: {status['per_key']['remaining']}")
    print()

    # [BUG-007] Race condition under concurrent load
    print("⚠️  [BUG-007] Race condition in concurrent requests!")
    print("   Under load, multiple requests can bypass rate limit\n")

    # Reset and demonstrate the issue
    rl.reset(test_key_id)
    print("✅ Testing concurrent requests (simulating race condition)...")

    # Fire 10 concurrent requests against 5/minute limit
    results = await asyncio.gather(*[rl.check(test_key_id) for _ in range(10)])
    allowed_count = sum(results)
    print(f"   Expected: 5 allowed, 5 blocked")
    print(f"   Actual: {allowed_count} allowed, {10-allowed_count} blocked")
    if allowed_count > 5:
        print(f"   ⚠️  Race condition: {allowed_count - 5} extra requests leaked through!")
    print()


# ============================================================================
# 3. AUDIT LOGGING DEMO
# ============================================================================


async def demo_audit_logging():
    """Demonstrate audit logging with file and SQLite backends."""
    section("3. AUDIT LOGGING")

    # Create temporary files for demo
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        file_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name

    print(f"📋 Creating audit logs:")
    print(f"   File: {file_path}")
    print(f"   SQLite: {db_path}\n")

    # [BUG-009] Synchronous I/O blocks event loop
    print("⚠️  [BUG-009] File and SQLite backends use blocking I/O")
    print("   This blocks the event loop and degrades performance\n")

    # Test file backend
    print("✅ Testing file (JSONL) backend...")
    file_audit = AuditLog(backend="file", path=file_path)

    record1 = AuditRecord(
        key_id="key_abc",
        key_name="test-key",
        tool="get_data",
        scopes=["read:data"],
        duration_ms=42.5,
        status="ok",
        input_args={"query": "test"},
        output_preview="Result: 123",
    )

    await file_audit.write(record1)
    print("   ✓ Wrote audit record to JSONL file")

    # Verify file contents
    with open(file_path) as f:
        lines = f.readlines()
        print(f"   ✓ File contains {len(lines)} record(s)")
        print(f"   First line: {lines[0][:80]}...")
    print()

    # Test SQLite backend (queryable)
    print("✅ Testing SQLite backend (queryable)...")
    sqlite_audit = AuditLog(backend="sqlite", path=db_path)

    # Write multiple records
    for i in range(3):
        record = AuditRecord(
            key_id="key_xyz",
            key_name=f"test-key-{i}",
            tool=f"tool_{i}",
            scopes=["read:data"],
            duration_ms=10.0 + i,
            status="ok",
        )
        await sqlite_audit.write(record)
    print(f"   ✓ Wrote 3 records to SQLite\n")

    # Query records back
    print("✅ Querying audit records...")
    records = await sqlite_audit.query(key_id="key_xyz", limit=10)
    print(f"   ✓ Found {len(records)} records for key_id='key_xyz'")
    for r in records:
        print(f"   - {r.tool}: {r.status} ({r.duration_ms}ms)")
    print()

    # [BUG-002] Audit logging doesn't work with Guard
    print("⚠️  [BUG-002] CRITICAL: Audit logging never writes in Guard!")
    print("   KeyStoreVerifier receives AuditLog but never calls write()")
    print("   These manual tests work, but Guard integration is broken\n")

    # Cleanup
    Path(file_path).unlink()
    Path(db_path).unlink()


# ============================================================================
# 4. IP POLICY DEMO
# ============================================================================


def demo_ip_policy():
    """Demonstrate IP allowlist/denylist policy."""
    section("4. IP POLICY")

    print("🌐 Creating IP policy (allow internal network, deny specific subnet)\n")

    policy = IPPolicy(
        allow=["10.0.0.0/8", "192.168.0.0/16"],
        deny=["10.99.0.0/16"]  # Block specific subnet within allowlist
    )

    test_cases = [
        ("10.0.1.5", True, "Internal network (allowed)"),
        ("192.168.1.100", True, "Internal network (allowed)"),
        ("10.99.0.50", False, "Denied subnet (blocked)"),
        ("8.8.8.8", False, "External IP (not in allowlist)"),
        ("invalid-ip", False, "Invalid IP address"),
    ]

    print("✅ Testing IP policy rules:")
    for ip, expected, description in test_cases:
        result = policy.is_allowed(ip)
        status = "✓ ALLOWED" if result else "✗ BLOCKED"
        match = "✓" if result == expected else "✗ UNEXPECTED"
        print(f"   {match} {ip:20s} → {status:12s} ({description})")
    print()

    # [BUG-003] IP policy never enforced in Guard
    print("⚠️  [BUG-003] CRITICAL: IP policy is never enforced!")
    print("   KeyStoreVerifier receives IPPolicy but never calls is_allowed()")
    print("   This demo works, but Guard integration is broken\n")


# ============================================================================
# 5. BUG DEMONSTRATIONS
# ============================================================================


def demo_bugs():
    """Demonstrate known bugs with clear reproduction cases."""
    section("5. BUG DEMONSTRATIONS")

    # BUG-001: Missing backends
    print("🐛 [BUG-001] SQLite backend doesn't exist\n")
    try:
        store = KeyStore(backend="sqlite", path="test.db")
        print("   ✗ Unexpected: SQLite backend loaded!")
    except ModuleNotFoundError as e:
        print(f"   ✓ Expected crash: {e}\n")

    # BUG-006: O(n) bcrypt verification
    print("🐛 [BUG-006] O(n) bcrypt verification DoS")
    print("   Creating 10 keys and timing verification...\n")

    import time
    store = KeyStore(backend="memory")

    # Create multiple keys
    for i in range(10):
        store.create(name=f"key-{i}", scopes=["test"])

    # Time verification with invalid token (checks all keys)
    start = time.perf_counter()
    result = store.verify("fmg_sk_invalid_token_xxxxxxxxxxxxxx")
    elapsed = time.perf_counter() - start

    print(f"   Time to verify invalid token: {elapsed*1000:.1f}ms")
    print(f"   With 10 keys: ~{elapsed*1000:.1f}ms")
    print(f"   With 100 keys: ~{elapsed*10*1000:.1f}ms (estimated)")
    print(f"   With 1000 keys: ~{elapsed*100*1000:.1f}ms (estimated)")
    print("   ⚠️  Linear scaling = DoS amplification!\n")

    # BUG-008: Decorator breaks sync functions
    print("🐛 [BUG-008] @rate_limit decorator breaks sync functions")
    print("   (Cannot demo without patching — would crash)\n")

    # BUG-010: Missing bcrypt dependency
    print("🐛 [BUG-010] bcrypt not in pyproject.toml dependencies")
    print("   Check pyproject.toml — bcrypt is imported but not listed")
    print("   Fresh installs will crash on first key operation\n")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


async def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("  fastmcp-guard COMPREHENSIVE DEMO")
    print("="*60)
    print("\nThis demo exercises all components and demonstrates bugs.")
    print("See BUGS.md for detailed bug reports.\n")

    # Run synchronous demos
    demo_key_lifecycle()
    demo_ip_policy()
    demo_bugs()

    # Run async demos
    await demo_rate_limiting()
    await demo_audit_logging()

    # Final summary
    section("SUMMARY")
    print("✅ Tested features:")
    print("   - Key lifecycle (create, verify, rotate, revoke)")
    print("   - Rate limiting (per-key and global)")
    print("   - Audit logging (file and SQLite backends)")
    print("   - IP policy (allow/deny rules)")
    print()
    print("⚠️  Critical bugs found:")
    print("   - [BUG-001] Only memory backend works (sqlite/postgres/redis missing)")
    print("   - [BUG-002] Audit logging never writes in Guard (completely broken)")
    print("   - [BUG-003] IP policy never enforced in Guard (completely broken)")
    print("   - [BUG-006] bcrypt O(n) verification = DoS vulnerability")
    print("   - [BUG-007] Rate limiter race condition under concurrent load")
    print()
    print("📖 See BUGS.md for full details and reproduction steps")
    print()


if __name__ == "__main__":
    asyncio.run(main())
