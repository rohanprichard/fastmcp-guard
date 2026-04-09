# fastmcp-guard Bug Report

This document catalogs all bugs and vulnerabilities discovered during code review and testing.

## Summary Table

| ID | Severity | Status | Description |
|----|----------|--------|-------------|
| BUG-001 | CRITICAL | Open | SQLite/Postgres/Redis key backends not implemented |
| BUG-002 | CRITICAL | Open | Audit logging is completely non-functional (never writes) |
| BUG-003 | CRITICAL | Open | IP policy is never enforced |
| BUG-004 | HIGH | Open | @rate_limit decorator is a no-op |
| BUG-005 | HIGH | Open | Grace period keys never expire (no background task) |
| BUG-006 | SECURITY | Open | O(n) bcrypt verification = DoS amplification |
| BUG-007 | SECURITY | Open | Race condition in rate limiter (check+append not atomic) |
| BUG-008 | BUG | Open | @rate_limit decorator breaks sync tool functions |
| BUG-009 | BUG | Open | Synchronous I/O blocks the event loop |
| BUG-010 | BUG | Open | bcrypt missing from pyproject.toml dependencies |

---

## BUG-001 — CRITICAL: SQLite/Postgres/Redis key backends not implemented

**File:** `src/fastmcp_guard/keys/store.py:53-67`

### Description
The `KeyStore._init_backend()` method attempts to import backend implementations that don't exist:
- `fastmcp_guard.keys.backends.sqlite.SQLiteBackend` → ModuleNotFoundError
- `fastmcp_guard.keys.backends.postgres.PostgresBackend` → ModuleNotFoundError
- `fastmcp_guard.keys.backends.redis.RedisBackend` → ModuleNotFoundError

Only the in-memory backend is implemented. The CLI defaults to SQLite, causing immediate crashes.

### Impact
- **Critical**: Any production deployment will fail
- Only memory backend works (dev-only, data lost on restart)
- All documentation examples using `backend="sqlite"` are broken

### Reproduction
```python
from fastmcp_guard import KeyStore

# This crashes immediately:
store = KeyStore(backend="sqlite", path="test.db")
# ModuleNotFoundError: No module named 'fastmcp_guard.keys.backends.sqlite'
```

### Suggested Fix
1. Implement `src/fastmcp_guard/keys/backends/sqlite.py` with `SQLiteBackend` class
2. Implement schema migration and bcrypt hash storage
3. Or: Document memory-only limitation and remove sqlite from type hints

---

## BUG-002 — CRITICAL: Audit logging is completely non-functional (never writes)

**File:** `src/fastmcp_guard/keys/verifier.py`

### Description
`KeyStoreVerifier.__init__` receives `self._audit` (AuditLog instance) but `verify_token()` never calls `audit.write()`. There are no tool call hooks or middleware to intercept requests. The AuditLog is wired up but completely dead.

### Impact
- **Critical**: Audit logging feature is advertised but completely non-functional
- No tool calls are logged regardless of audit configuration
- Compliance/security requirements cannot be met
- Silent failure (no errors, just no logs)

### Reproduction
```python
from fastmcp_guard import Guard, KeyStore, AuditLog
from fastmcp import FastMCP

mcp = FastMCP("test")
guard = Guard(
    mcp,
    keys=KeyStore(),
    audit=AuditLog(backend="file", path="audit.jsonl")
)

# Create and use a key... audit.jsonl stays empty
# No audit records are ever written
```

### Suggested Fix
1. Add middleware/hook in `Guard._install()` to intercept tool calls
2. In the middleware, call `audit.write()` with AuditRecord for each request
3. Extract client IP, timing, inputs/outputs from request context

---

## BUG-003 — CRITICAL: IP policy is never enforced

**File:** `src/fastmcp_guard/keys/verifier.py`

### Description
`KeyStoreVerifier.__init__` receives `self._ip` (IPPolicy instance) but `verify_token()` never calls `self._ip.is_allowed()`. No client IP is extracted from the request context or checked against the policy.

### Impact
- **Critical**: IP allowlisting feature is completely non-functional
- Blocked IPs can access the server freely
- Security controls are bypassed silently

### Reproduction
```python
from fastmcp_guard import Guard, KeyStore, IPPolicy
from fastmcp import FastMCP

mcp = FastMCP("test")
guard = Guard(
    mcp,
    keys=KeyStore(),
    ip=IPPolicy(allow=["10.0.0.0/8"])  # Only allow internal network
)

# Requests from 8.8.8.8 will succeed — IP policy is ignored
```

### Suggested Fix
1. Extract client IP from FastMCP request context in `verify_token()`
2. Call `self._ip.is_allowed(client_ip)` after key verification
3. Raise `AuthorizationError` if IP is not allowed

---

## BUG-004 — HIGH: @rate_limit decorator is a no-op

**File:** `src/fastmcp_guard/rate/decorator.py` + `src/fastmcp_guard/keys/verifier.py`

### Description
The `@rate_limit` decorator attaches `__fastmcp_guard_rate_limit__ = "10/minute"` metadata to functions, but nothing reads these markers. There's no middleware that intercepts tool dispatch to check this attribute.

### Impact
- **High**: Per-tool rate limits are never enforced
- Tools marked with @rate_limit have no actual rate limiting applied
- Only per-key global rate limiting works

### Reproduction
```python
from fastmcp import FastMCP
from fastmcp_guard.rate import rate_limit

mcp = FastMCP("test")

@mcp.tool
@rate_limit("2/minute")  # This does nothing
async def expensive_tool(query: str) -> str:
    return "result"

# Can call expensive_tool 1000 times/minute — decorator is ignored
```

### Suggested Fix
1. Add middleware in `Guard._install()` that inspects the called tool
2. Check for `__fastmcp_guard_rate_limit__` attribute on the tool function
3. Apply a separate RateLimit instance for that tool+key combination

---

## BUG-005 — HIGH: Grace period keys never expire (no background task)

**File:** `src/fastmcp_guard/keys/store.py`

### Description
`KeyStore._expire_grace_periods()` exists but is never called automatically. There's no background asyncio.Task, no scheduler, no hooks. Keys marked as `ROTATING` with a grace period stay in that state forever — old tokens remain valid indefinitely.

### Impact
- **High**: Key rotation is broken
- Old tokens never expire after rotation, defeating the purpose
- Security risk: compromised keys cannot be effectively rotated out

### Reproduction
```python
from fastmcp_guard import KeyStore
import asyncio
from datetime import datetime, timezone

store = KeyStore()
key1 = store.create(name="test")
token1 = key1.token

# Rotate with 0-hour grace period (should expire immediately)
key2 = store.rotate(key1.id, grace_period_hours=0)

# Wait for grace period to pass
await asyncio.sleep(1)

# token1 still validates! Grace period never processed
assert store.verify(token1) is not None  # SHOULD be None
```

### Suggested Fix
1. Start a background `asyncio.Task` in `Guard.__init__()`
2. Task periodically calls `keys._expire_grace_periods()` (e.g. every 60s)
3. Or: Check grace periods on each `verify()` call (simpler but less efficient)

---

## BUG-006 — SECURITY: O(n) bcrypt verification = DoS amplification

**File:** `src/fastmcp_guard/keys/store.py:115-137` (verify method)

### Description
The `verify()` method iterates through ALL keys in `_store` and calls `bcrypt.checkpw()` on each one. bcrypt is intentionally slow (~100ms per check). With 100 keys, every auth request takes ~10 seconds (serial). An attacker can send invalid tokens to exhaust CPU linearly with key count.

### Impact
- **Security**: DoS amplification attack vector
- Performance degrades linearly with number of keys
- Even legitimate requests slow down as key count grows
- 1000 keys = 100 seconds per auth attempt

### Attack Scenario
```python
# Attacker sends invalid tokens repeatedly
for _ in range(1000):
    store.verify("fmg_sk_invalid_token_xxxxxxxx")
    # Each call iterates 100 keys × 100ms = 10 seconds
    # = 10,000 seconds of CPU time per 1000 requests
```

### Suggested Fix
Store a fast lookup index mapping `token_prefix → [candidate_keys]`:
1. On `create()`, extract first 8 chars of token, add to index
2. On `verify()`, lookup candidates by prefix, only bcrypt check those
3. Reduces from O(n) to O(1) in average case

---

## BUG-007 — SECURITY: Race condition in rate limiter (check+append not atomic)

**File:** `src/fastmcp_guard/rate/limiter.py:77-98` (check method)

### Description
The `check()` method performs non-atomic read-modify-write:
1. `_slide()` to count current requests
2. Check if under limit
3. `append()` timestamp to window

Under concurrent load, multiple requests can pass step 2 before any reach step 3, allowing burst beyond the rate limit.

### Impact
- **Security**: Rate limit bypass under concurrent load
- Can cause resource exhaustion if limit was set for protection
- Affects both per-key and global limits

### Attack Scenario
```python
# Attacker sends 100 concurrent requests against 10/minute limit
# All 100 check simultaneously, see 0 requests in window
# All 100 pass the check and get appended
# Rate limit bypassed: 100 requests instead of 10
```

### Suggested Fix
Use `asyncio.Lock()` to make check+record atomic:
```python
async def check(self, key_id: str) -> bool:
    async with self._lock:  # Make entire check+append atomic
        now = time.monotonic()
        # ... existing logic ...
```

---

## BUG-008 — BUG: @rate_limit decorator breaks sync tool functions

**File:** `src/fastmcp_guard/rate/decorator.py:34-35`

### Description
The decorator's wrapper is `async def` and unconditionally does `await fn(*args, **kwargs)`. If `fn` is a regular synchronous function, this raises:
- `TypeError: object int can't be used in 'await' expression` (for functions returning values)
- `TypeError: object NoneType can't be used in 'await' expression` (for void functions)

### Impact
- **Bug**: Decorator cannot be used with sync functions
- Crashes at runtime when decorated sync tool is called
- Limits decorator to async functions only

### Reproduction
```python
from fastmcp_guard.rate import rate_limit

@rate_limit("10/minute")
def sync_tool(x: int) -> int:  # Sync function
    return x * 2

await sync_tool(5)  # TypeError: object int can't be used in 'await' expression
```

### Suggested Fix
Check if function is async before awaiting:
```python
import inspect

@functools.wraps(fn)
async def wrapper(*args, **kwargs):
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    else:
        return fn(*args, **kwargs)
```

---

## BUG-009 — BUG: Synchronous I/O blocks the event loop

**Files:**
- `src/fastmcp_guard/audit/backends/file.py:28-31` (open() is blocking)
- `src/fastmcp_guard/audit/backends/sqlite.py:53-70` (sqlite3.connect() is blocking)

### Description
Both file and SQLite audit backends perform synchronous I/O inside `async def write()` methods:
- `file.py`: Uses blocking `open()` for file I/O
- `sqlite.py`: Uses blocking `sqlite3.connect()` and `execute()`

This blocks the entire event loop during I/O operations, degrading performance and potentially causing timeouts.

### Impact
- **Bug**: Event loop blocking degrades async performance
- High-throughput servers will experience latency spikes
- Can cause request timeouts under load

### Performance Impact
```python
# With 100 concurrent requests writing audit logs:
# - Async I/O: all complete in ~10ms (parallel)
# - Sync I/O: complete in 100×10ms = 1000ms (serial blocking)
```

### Suggested Fix

**For file.py:** Use `asyncio.to_thread()` or `aiofiles`:
```python
async def write(self, record: AuditRecord) -> None:
    async with self._lock:
        await asyncio.to_thread(self._write_sync, record)

def _write_sync(self, record: AuditRecord) -> None:
    with self._path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict()) + "\n")
```

**For sqlite.py:** Use `run_in_executor()` or `aiosqlite`:
```python
async def write(self, record: AuditRecord) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, self._write_sync, record)
```

---

## BUG-010 — BUG: bcrypt missing from pyproject.toml dependencies

**File:** `pyproject.toml:25-31`

### Description
`bcrypt` is used in `KeyStore.create()` and `verify()` for hashing tokens, but it's NOT listed in the `dependencies` array in `pyproject.toml`. The package will install successfully via pip, but fail at runtime when any key operations are performed.

### Impact
- **Bug**: RuntimeError when using keys in fresh installations
- Poor user experience (installs fine, fails on first use)
- Confusing error message for users

### Reproduction
```bash
pip install fastmcp-guard  # Succeeds
python -c "from fastmcp_guard import KeyStore; KeyStore().create('test')"
# ModuleNotFoundError: No module named 'bcrypt'
```

### Suggested Fix
Add bcrypt to dependencies in `pyproject.toml`:
```toml
dependencies = [
    "fastmcp>=2.0",
    "pydantic>=2.0",
    "typer>=0.12",
    "rich>=13.0",
    "anyio>=4.0",
    "bcrypt>=4.0",  # ADD THIS
]
```

---

## Testing Recommendations

1. **Add integration tests** for each critical feature (audit, IP policy, rate limiting)
2. **Add backend implementations** or remove them from type hints/docs
3. **Add concurrency tests** for race conditions in rate limiter
4. **Add performance benchmarks** to catch O(n) bcrypt issue early
5. **Enable stricter linting** to catch blocking I/O in async functions

## Priority Order

**Immediate (before any production use):**
1. BUG-001 - Implement backends or remove from docs
2. BUG-002 - Fix audit logging (critical feature)
3. BUG-003 - Fix IP policy enforcement
4. BUG-010 - Add bcrypt dependency

**High priority (before v1.0):**
1. BUG-006 - Fix bcrypt DoS amplification
2. BUG-007 - Fix rate limiter race condition
3. BUG-004 - Implement @rate_limit decorator support
4. BUG-005 - Implement grace period expiry

**Medium priority:**
1. BUG-008 - Fix decorator for sync functions
2. BUG-009 - Make I/O async

---

*Generated during fastmcp-guard POC development — see `examples/walkthrough/` for reproduction steps*
