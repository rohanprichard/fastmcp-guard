# fastmcp-guard Walkthrough

This walkthrough demonstrates all features of fastmcp-guard through three different demos. Each demo is heavily commented and shows both working features and known bugs.

## 🎯 What You'll Learn

1. **Key Management**: Create, verify, rotate, and revoke API keys
2. **Rate Limiting**: Per-key and global rate limits with sliding windows
3. **Audit Logging**: File (JSONL) and SQLite backends
4. **IP Policy**: Allowlist/denylist for network access control
5. **Known Bugs**: Where the implementation breaks and why

## 📋 Prerequisites

1. **Install dependencies**:
   ```bash
   # From repo root
   .venv/bin/python -m pip install -e .
   .venv/bin/python -m pip install httpx  # For HTTP client demo
   ```

2. **Verify installation**:
   ```bash
   .venv/bin/python -c "from fastmcp_guard import Guard; print('✓ Installed')"
   ```

## 🚀 Demo 1: Standalone Component Tests

**File**: `demo.py`
**What it does**: Tests each component individually (no HTTP server needed)
**Best for**: Understanding how each feature works in isolation

### Run It

```bash
.venv/bin/python examples/walkthrough/demo.py
```

### What It Demonstrates

#### 1. Key Lifecycle

- ✅ **Create** a new API key with scopes and metadata
- ✅ **Verify** tokens (bcrypt hash check)
- ✅ **Rotate** keys with grace period
- ✅ **Revoke** keys immediately
- ⚠️ **[BUG-001]**: SQLite backend crashes — only memory backend works
- ⚠️ **[BUG-005]**: Grace periods never expire (old tokens valid forever)
- ⚠️ **[BUG-006]**: O(n) bcrypt verification = DoS amplification

#### 2. Rate Limiting

- ✅ **Per-key limits** enforce request quotas
- ✅ **Global limits** protect server capacity
- ✅ **Sliding window** algorithm (counts requests in past N seconds)
- ⚠️ **[BUG-007]**: Race condition under concurrent load

#### 3. Audit Logging

- ✅ **File backend** writes JSONL (one record per line)
- ✅ **SQLite backend** writes queryable records
- ✅ **Query API** filters by key, tool, time range
- ⚠️ **[BUG-002]**: Guard never calls `audit.write()` — completely broken
- ⚠️ **[BUG-009]**: Backends use blocking I/O (slow event loop)

#### 4. IP Policy

- ✅ **Allowlist** restricts access to specific IPs/CIDR ranges
- ✅ **Denylist** blocks specific IPs even if in allowlist
- ⚠️ **[BUG-003]**: Guard never checks IP policy — completely broken

#### 5. Bug Demonstrations

- Proves each bug with reproducible test cases
- Shows performance impact (e.g., bcrypt O(n) scaling)

### Expected Output

```
==============================================================
  fastmcp-guard COMPREHENSIVE DEMO
==============================================================

This demo exercises all components and demonstrates bugs.
See BUGS.md for detailed bug reports.

==============================================================
  1. KEY LIFECYCLE
==============================================================

🔑 Creating in-memory KeyStore
   ⚠️  [BUG-001] SQLite backend crashes — only memory backend works

✅ Creating new API key...
   Key ID: fmg_key_...
   Token: fmg_sk_... (only shown once!)
   ...

[continues with detailed output for each section]
```

---

## 🌐 Demo 2: HTTP Server & Client POC

**Files**: `poc_server.py` + `poc_client.py`
**What it does**: Full end-to-end HTTP demo with real authentication
**Best for**: Testing Guard with FastMCP over HTTP

### Run It

**Terminal 1 — Start the server**:
```bash
.venv/bin/python examples/walkthrough/poc_server.py
```

Server will print API keys on startup:
```
🔑 Creating demo API key...
   Token: fmg_sk_abc123...
   Key ID: fmg_key_xyz789

   💾 Save this token for poc_client.py!
```

**Terminal 2 — Run the client**:
```bash
.venv/bin/python examples/walkthrough/poc_client.py
```

The client will prompt for tokens (copy from server output).

### What It Tests

#### Test 1: Unauthenticated Request → 401
- Sends request WITHOUT `Authorization` header
- ✅ Server correctly rejects with 401

#### Test 2: Valid Token → 200
- Sends requests WITH valid Bearer token
- ✅ Calls both async (`get_data`) and sync (`calculate`) tools
- ✅ Authentication works correctly

#### Test 3: Revoked Token → 401
- Uses a pre-revoked key
- ✅ Server correctly rejects with 401

#### Test 4: Rate Limit → 429
- Sends 7 requests against 5/minute limit
- ✅ First 5 succeed, 6th and 7th fail with 429
- ⚠️ **[BUG-007]**: Under concurrent load, more than 5 might succeed (race condition)

#### Test 5: Per-Tool Rate Limit → BROKEN
- Calls `expensive_analysis` (decorated with `@rate_limit("2/minute")`)
- Can send 100 requests — decorator is ignored
- ⚠️ **[BUG-004]**: `@rate_limit` decorator is a no-op

### Known Issues in HTTP Demo

1. **[BUG-002]**: Check `poc_audit.jsonl` after running — it stays empty (audit never writes)
2. **[BUG-003]**: Connect from non-localhost IP — it works (IP policy ignored)
3. **[BUG-004]**: `expensive_analysis` has no per-tool rate limit

---

## 🎨 Demo 3: Full-Featured Server

**File**: `server.py`
**What it does**: Production-like configuration with all features enabled
**Best for**: Seeing the intended configuration (even though some features are broken)

### Run It

```bash
.venv/bin/python examples/walkthrough/server.py
```

### Features Configured

- ✅ **KeyStore**: Memory backend (3 demo keys created)
- ✅ **RateLimit**: 100/minute per-key, 1000/minute global
- ⚠️ **AuditLog**: Configured but never writes [BUG-002]
- ⚠️ **IPPolicy**: Localhost-only configured but not enforced [BUG-003]

### Available Tools

1. `get_server_time()` — async, returns current UTC time
2. `add_numbers(a, b)` — sync, adds two integers
3. `fetch_data(resource_id)` — async, simulates data fetch
4. `calculate_stats(values)` — sync, computes min/max/mean
5. `expensive_operation(query)` — async with `@rate_limit` decorator (broken)
6. `simulate_long_task(duration_seconds)` — async, sleeps for N seconds

### API Keys Created

On startup, server prints 3 keys:

1. **admin-key**: Full scopes (`read:*`, `write:*`, `admin:*`)
2. **readonly-key**: Read-only scope (`read:data`)
3. **rotate-test-key**: Rotated with 1-hour grace (old token still works forever)

### Testing

Use the printed tokens with any MCP client or HTTP client:

```bash
# Example with curl (replace TOKEN)
curl -X POST http://127.0.0.1:8000/mcp/v1/tools/call \
  -H "Authorization: Bearer fmg_sk_YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"name": "get_server_time", "arguments": {}}'
```

---

## 🐛 Known Limitations

All demos document bugs inline with `[BUG-XXX]` markers. See **BUGS.md** at repo root for:

- Detailed descriptions
- Reproduction steps
- Suggested fixes
- Priority order

### Critical Bugs (Block Production Use)

1. **[BUG-001]**: SQLite/Postgres/Redis backends don't exist
2. **[BUG-002]**: Audit logging completely non-functional
3. **[BUG-003]**: IP policy never enforced

### High Priority Bugs

4. **[BUG-004]**: `@rate_limit` decorator is a no-op
5. **[BUG-005]**: Grace periods never expire

### Security Issues

6. **[BUG-006]**: bcrypt O(n) verification = DoS vector
7. **[BUG-007]**: Rate limiter race condition

### Standard Bugs

8. **[BUG-008]**: Decorator breaks sync functions
9. **[BUG-009]**: Blocking I/O in async functions
10. **[BUG-010]**: bcrypt missing from dependencies

---

## 📊 What Works vs. What's Broken

| Feature | Component Tests (demo.py) | HTTP Demo (poc_*.py) | Status |
|---------|--------------------------|---------------------|--------|
| **Key creation** | ✅ Works | ✅ Works | ✅ Working |
| **Key verification** | ✅ Works | ✅ Works | ✅ Working |
| **Key rotation** | ⚠️ Grace never expires | ⚠️ Grace never expires | ⚠️ Partial |
| **Key revocation** | ✅ Works | ✅ Works | ✅ Working |
| **Per-key rate limit** | ✅ Works | ✅ Works | ✅ Working |
| **Global rate limit** | ✅ Works | ✅ Works | ✅ Working |
| **@rate_limit decorator** | ❌ No-op | ❌ No-op | ❌ Broken |
| **Audit logging** | ✅ Manual write works | ❌ Guard never calls it | ❌ Broken |
| **IP policy** | ✅ Manual check works | ❌ Guard never calls it | ❌ Broken |
| **SQLite backend** | ❌ Crashes | ❌ Crashes | ❌ Broken |

---

## 🔍 Debugging Tips

### Check Audit Logs

After running `poc_server.py` or `server.py`:

```bash
# File backend (should be empty due to BUG-002)
cat poc_audit.jsonl
cat guard_demo_audit.jsonl

# SQLite backend (should be empty due to BUG-002)
sqlite3 guard_demo_audit.db "SELECT COUNT(*) FROM audit_log"
```

Expected: **0 records** (audit never writes)

### Verify Rate Limiting

```bash
# In Python
from fastmcp_guard import RateLimit
import asyncio

rl = RateLimit(per_key="5/minute")
key = "test"

# Should allow 5, then block
for i in range(7):
    allowed = asyncio.run(rl.check(key))
    print(f"Request {i+1}: {'✓' if allowed else '✗'}")
```

### Test bcrypt Performance

```bash
.venv/bin/python -c "
from fastmcp_guard import KeyStore
import time

store = KeyStore()
for i in range(100):
    store.create(name=f'key-{i}')

start = time.perf_counter()
store.verify('fmg_sk_invalid')
elapsed = (time.perf_counter() - start) * 1000
print(f'100 keys: {elapsed:.0f}ms per invalid token')
"
```

Expected: ~10,000ms (10 seconds) with 100 keys

---

## 💡 Next Steps

1. **Fix critical bugs** (BUG-001, BUG-002, BUG-003) before any production use
2. **Implement missing backends** or remove them from docs/type hints
3. **Add integration tests** that would have caught these bugs
4. **Fix security issues** (BUG-006, BUG-007) before handling untrusted traffic
5. **Add background task** for grace period expiry (BUG-005)

---

## 📚 Additional Resources

- **BUGS.md**: Comprehensive bug report with reproduction steps
- **README.md**: Project overview and installation
- **Source code**: `src/fastmcp_guard/` for implementation details

---

*This walkthrough is part of the fastmcp-guard POC demonstrating both working features and known limitations.*
