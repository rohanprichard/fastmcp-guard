#!/usr/bin/env python3
"""
POC client for testing the fastmcp-guard HTTP server.

This client demonstrates:
1. Unauthenticated request → 401
2. Authenticated request with valid key → 200
3. Revoked key → 401
4. Rate limit being hit → 429

Prerequisites:
1. Start poc_server.py first
2. Copy the demo token from server output

Run: .venv/bin/python examples/walkthrough/poc_client.py
"""

import sys
import asyncio
import httpx


# ============================================================================
# CONFIGURATION
# ============================================================================

SERVER_URL = "http://127.0.0.1:8765"

# These tokens are printed by poc_server.py on startup
# Copy them from the server output or use these placeholders
VALID_TOKEN = None  # Will be prompted if not set
REVOKED_TOKEN = None  # Will be prompted if not set


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


async def test_unauthenticated(client: httpx.AsyncClient):
    """Test 1: Request without authentication should fail with 401."""
    section("TEST 1: Unauthenticated Request")

    print("📤 Sending request WITHOUT Authorization header...")
    try:
        response = await client.post(
            f"{SERVER_URL}/mcp/v1/tools/call",
            json={
                "name": "get_data",
                "arguments": {"query": "test"}
            },
            timeout=5.0
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 401:
            print("   ✓ Correctly rejected (401 Unauthorized)\n")
        else:
            print(f"   ✗ Unexpected: {response.status_code}\n")
            print(f"   Response: {response.text[:200]}\n")
    except httpx.ConnectError:
        print("   ✗ Connection failed — is poc_server.py running?")
        print("   Start it with: .venv/bin/python examples/walkthrough/poc_server.py\n")
        sys.exit(1)
    except Exception as e:
        print(f"   ✗ Error: {e}\n")


async def test_valid_token(client: httpx.AsyncClient, token: str):
    """Test 2: Request with valid token should succeed."""
    section("TEST 2: Authenticated Request (Valid Token)")

    print(f"📤 Sending request WITH valid token...")
    print(f"   Token: {token[:30]}...\n")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Test async tool
        print("   Calling get_data(query='hello')...")
        response = await client.post(
            f"{SERVER_URL}/mcp/v1/tools/call",
            headers=headers,
            json={
                "name": "get_data",
                "arguments": {"query": "hello"}
            },
            timeout=5.0
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✓ Success! Response: {response.json()}")
        else:
            print(f"   ✗ Failed: {response.text[:200]}")
        print()

        # Test sync tool
        print("   Calling calculate(x=5, y=3)...")
        response = await client.post(
            f"{SERVER_URL}/mcp/v1/tools/call",
            headers=headers,
            json={
                "name": "calculate",
                "arguments": {"x": 5, "y": 3}
            },
            timeout=5.0
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✓ Success! Response: {response.json()}")
        else:
            print(f"   ✗ Failed: {response.text[:200]}")
        print()

    except Exception as e:
        print(f"   ✗ Error: {e}\n")


async def test_revoked_token(client: httpx.AsyncClient, token: str):
    """Test 3: Request with revoked token should fail with 401."""
    section("TEST 3: Revoked Token")

    print(f"📤 Sending request with REVOKED token...")
    print(f"   Token: {token[:30]}...\n")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = await client.post(
            f"{SERVER_URL}/mcp/v1/tools/call",
            headers=headers,
            json={
                "name": "get_data",
                "arguments": {"query": "test"}
            },
            timeout=5.0
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 401:
            print("   ✓ Correctly rejected (401 Unauthorized)")
            print(f"   Response: {response.text[:200]}\n")
        else:
            print(f"   ✗ Unexpected: Token should be revoked!")
            print(f"   Response: {response.text[:200]}\n")

    except Exception as e:
        print(f"   ✗ Error: {e}\n")


async def test_rate_limiting(client: httpx.AsyncClient, token: str):
    """Test 4: Hit rate limit (5 requests/minute)."""
    section("TEST 4: Rate Limiting")

    print("📤 Testing rate limit (5 requests/minute)...")
    print("   Sending 7 requests rapidly...\n")

    headers = {"Authorization": f"Bearer {token}"}

    results = []
    for i in range(7):
        try:
            response = await client.post(
                f"{SERVER_URL}/mcp/v1/tools/call",
                headers=headers,
                json={
                    "name": "get_data",
                    "arguments": {"query": f"test-{i}"}
                },
                timeout=5.0
            )
            status = response.status_code
            results.append(status)
            icon = "✓" if status == 200 else "✗"
            print(f"   {icon} Request {i+1}: {status}")

            # Stop after first rate limit hit
            if status == 429:
                print(f"   ⚠️  Rate limited! (as expected)")
                break

        except Exception as e:
            print(f"   ✗ Request {i+1} error: {e}")
            results.append(0)

    print()
    allowed = sum(1 for s in results if s == 200)
    blocked = sum(1 for s in results if s == 429)
    print(f"   Summary: {allowed} allowed, {blocked} rate-limited")

    if blocked > 0:
        print("   ✓ Rate limiting is working!\n")
    else:
        print("   ⚠️  Expected some requests to be rate-limited")
        print("   Note: Rate limit is 5/minute per key\n")


async def test_per_tool_rate_limit(client: httpx.AsyncClient, token: str):
    """Test 5: Per-tool rate limit (should fail due to BUG-004)."""
    section("TEST 5: Per-Tool Rate Limit (@rate_limit decorator)")

    print("📤 Testing expensive_analysis (decorated with @rate_limit('2/minute'))...")
    print("   [BUG-004] This decorator is a no-op — it won't actually limit\n")

    headers = {"Authorization": f"Bearer {token}"}

    print("   Sending 4 requests to expensive_analysis...")
    print("   Expected: 2 allowed, 2 blocked (if working)")
    print("   Actual: All allowed (decorator is broken)\n")

    for i in range(4):
        try:
            response = await client.post(
                f"{SERVER_URL}/mcp/v1/tools/call",
                headers=headers,
                json={
                    "name": "expensive_analysis",
                    "arguments": {"data": f"test-data-{i}"}
                },
                timeout=5.0
            )
            status = response.status_code
            icon = "✓" if status == 200 else "✗"
            print(f"   {icon} Request {i+1}: {status}")

        except Exception as e:
            print(f"   ✗ Request {i+1} error: {e}")

    print()
    print("   ⚠️  All requests succeeded — per-tool rate limit not enforced!")
    print("   [BUG-004] @rate_limit decorator is a no-op\n")


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run all tests."""
    global VALID_TOKEN, REVOKED_TOKEN

    print("\n" + "="*60)
    print("  fastmcp-guard POC CLIENT")
    print("="*60)
    print()

    # Prompt for tokens if not set
    if not VALID_TOKEN:
        print("⚠️  VALID_TOKEN not set in poc_client.py")
        print("   Check poc_server.py output for 'poc-demo-key' token")
        token_input = input("\nEnter valid token (or press Enter to skip): ").strip()
        if token_input:
            VALID_TOKEN = token_input
        else:
            print("   Skipping tests that require valid token\n")

    if not REVOKED_TOKEN:
        print("\n⚠️  REVOKED_TOKEN not set in poc_client.py")
        print("   Check poc_server.py output for 'revoke-demo-key' token")
        token_input = input("\nEnter revoked token (or press Enter to skip): ").strip()
        if token_input:
            REVOKED_TOKEN = token_input
        else:
            print("   Skipping revoked token test\n")

    # Create HTTP client
    async with httpx.AsyncClient() as client:
        # Test 1: Unauthenticated (always runs)
        await test_unauthenticated(client)

        # Test 2: Valid token
        if VALID_TOKEN:
            await test_valid_token(client, VALID_TOKEN)
        else:
            print("\n⚠️  Skipping Test 2 (no valid token provided)\n")

        # Test 3: Revoked token
        if REVOKED_TOKEN:
            await test_revoked_token(client, REVOKED_TOKEN)
        else:
            print("\n⚠️  Skipping Test 3 (no revoked token provided)\n")

        # Test 4: Rate limiting (needs valid token)
        if VALID_TOKEN:
            await test_rate_limiting(client, VALID_TOKEN)
        else:
            print("\n⚠️  Skipping Test 4 (no valid token provided)\n")

        # Test 5: Per-tool rate limit (needs valid token)
        if VALID_TOKEN:
            await test_per_tool_rate_limit(client, VALID_TOKEN)
        else:
            print("\n⚠️  Skipping Test 5 (no valid token provided)\n")

    # Summary
    section("SUMMARY")
    print("✅ Tested features:")
    print("   - Unauthenticated requests → 401")
    if VALID_TOKEN:
        print("   - Valid token authentication → 200")
        print("   - Per-key rate limiting → 429 after limit")
    if REVOKED_TOKEN:
        print("   - Revoked token → 401")
    print()
    print("⚠️  Known issues demonstrated:")
    print("   - [BUG-002] Audit log file stays empty (never written)")
    print("   - [BUG-003] IP policy not enforced (any IP can connect)")
    print("   - [BUG-004] @rate_limit decorator doesn't work")
    print()
    print("📖 See BUGS.md for full bug details")
    print()


if __name__ == "__main__":
    asyncio.run(main())
