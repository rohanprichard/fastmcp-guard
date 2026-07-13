# fastmcp-guard — Usage Guide

An operational layer for [FastMCP](https://github.com/jlowin/fastmcp) servers:
API-key lifecycle, rate limiting, audit logging, and IP policy — added as a
wrapper around your server, with **no changes to your tool code**.

This guide covers everything that works in v0.2. For the roadmap (Postgres/Redis,
OTel), see the status table in the [README](README.md).

---

## 1. Install

```bash
pip install fastmcp-guard
```

Requires Python ≥ 3.10 and FastMCP ≥ 2.0. `bcrypt` is installed automatically.

---

## 2. Quickstart

```python
from fastmcp import FastMCP
from fastmcp_guard import Guard, KeyStore, RateLimit, AuditLog

mcp = FastMCP("my-server")

@mcp.tool
def get_data(query: str) -> str:
    return f"Results for: {query}"

guard = Guard(
    mcp,
    keys=KeyStore(backend="sqlite", path="keys.db"),
    rate_limit=RateLimit(per_key="100/minute"),
    audit=AuditLog(backend="file", path="audit.jsonl"),
)

# Issue a key (print the token once — it's never retrievable again)
key = guard.keys.create(name="alice", scopes=["read:data"])
print("TOKEN:", key.token)  # fmg_sk_...

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
```

Clients authenticate with the token as a Bearer header:

```
Authorization: Bearer fmg_sk_<selector>.<secret>
```

> **Ordering note:** create the `Guard` *before* you serve the app. `Guard`
> installs FastMCP's auth provider and middleware at construction time, and
> FastMCP reads them when it builds the HTTP app.

---

## 3. What `Guard` does

`Guard(mcp, ...)` installs two things:

1. **Authentication** — a `TokenVerifier` that validates the Bearer token against
   your `KeyStore` and attaches the key's identity + scopes to the request.
2. **Ops middleware** — a FastMCP `Middleware` that, on every tool call, enforces
   IP policy, applies per-key and per-tool rate limits, and writes an audit
   record.

All four features are optional. Pass only what you need:

```python
Guard(mcp, keys=KeyStore(backend="sqlite", path="keys.db"))       # just auth
Guard(mcp, rate_limit=RateLimit(per_key="60/minute"))             # just limits
Guard(mcp, audit=AuditLog(backend="file", path="audit.jsonl"))    # just audit
```

---

## 4. API key management

Everything is on `guard.keys` (a `KeyStore`). You can also construct a
`KeyStore` standalone for scripts/CLIs.

```python
# Create — token is populated ONCE on the returned object
key = guard.keys.create(
    name="ci-bot",
    scopes=["read:builds", "write:builds"],
    expires_in_days=90,            # optional; None = never
    metadata={"team": "platform"}, # optional; surfaces in audit records
)
print(key.token)   # fmg_sk_...   store it now
print(key.id)      # fmg_key_...  use this for rotate/revoke

# List (tokens are never returned again)
for k in guard.keys.list():
    print(k.id, k.name, k.status, k.scopes)

# Inspect one
k = guard.keys.get(key.id)

# Rotate — issue a replacement; old key stays valid for the grace window,
# then is revoked automatically (checked lazily on each verify).
new_key = guard.keys.rotate(key.id, grace_period_hours=24)  # 0 = revoke now

# Revoke immediately
guard.keys.revoke(new_key.id)
```

**Scopes** are attached to the identity and exposed to FastMCP's authorization
layer and to your audit log. Enforce them in FastMCP however you normally would
(e.g. scope checks), or read them from the access token in a tool.

**Security model:** tokens are bcrypt-hashed and never stored in plaintext. Each
token carries a public *selector*, so verification is O(1) (one indexed lookup +
one bcrypt check) regardless of how many keys exist.

---

## 5. Rate limiting

### Per-key and global

```python
from fastmcp_guard import RateLimit

RateLimit(
    per_key="100/minute",      # per authenticated identity
    global_limit="2000/minute" # across all callers
)
```

Rate strings are `"<count>/<unit>"` where unit ∈ `second | minute | hour | day`.
The limiter is a sliding window and is concurrency-safe (check + record are
atomic).

### Per-tool overrides

Put a tighter ceiling on specific (usually expensive) tools. Enforced per
(key, tool), on top of the per-key limit. Works on sync and async tools:

```python
from fastmcp_guard.rate import rate_limit

@mcp.tool
@rate_limit("10/minute")   # decorator goes *below* @mcp.tool
def run_expensive_analysis(data: str) -> str:
    ...
```

> Order matters: `@mcp.tool` on top, `@rate_limit(...)` directly on the function.

When a limit is exceeded the tool call is rejected and an audit record with
status `rate_limited` is written.

---

## 6. Audit logging

A structured record is written for every tool call:

```json
{"ts": "2026-07-13T14:00:00Z", "key_id": "fmg_key_ab12",
 "key_name": "alice", "tool": "get_data", "scopes": ["read:data"],
 "duration_ms": 42.1, "status": "ok", "error": null,
 "input_args": {"query": "hi"}, "output_preview": "Results for: hi",
 "client_ip": "203.0.113.7", "metadata": {"team": "platform"}}
```

`status` is one of `ok | error | rate_limited | unauthorized`.

### Backends

```python
from fastmcp_guard import AuditLog

AuditLog(backend="file",   path="audit.jsonl")   # append-only JSONL
AuditLog(backend="sqlite", path="audit.db")      # queryable (see below)
AuditLog(backend="http",   url="https://siem.example/ingest")  # webhook/SIEM
```

### Redaction (do this before logging PII)

```python
AuditLog(backend="file", path="audit.jsonl",
         log_inputs=False,    # drop tool arguments from records
         log_outputs=False)   # drop the output preview
```

### Querying (SQLite backend only)

```python
audit = AuditLog(backend="sqlite", path="audit.db")
# ... after some traffic ...
records = await audit.query(key_name="alice", tool="get_data", limit=50)
```

---

## 7. IP allowlisting / denylisting

Enforced on each tool call **when a client IP is available** (i.e. HTTP
transports; stdio/in-memory have no IP and are not filtered).

```python
from fastmcp_guard import IPPolicy

IPPolicy(
    allow=["10.0.0.0/8", "192.168.1.100"],  # if set, ONLY these pass
    deny=["10.99.0.0/16"],                   # checked first; wins over allow
)
```

Rules: deny is evaluated first. If an allowlist is present, only matching IPs
pass; if no allowlist is set, everything not denied passes. Blocked calls get an
`unauthorized` audit record.

---

## 8. Using with OAuth / JWT

fastmcp-guard is **not** an OAuth server — under the MCP spec your server is an
OAuth 2.1 resource server that validates externally-issued tokens, and FastMCP
already provides `JWTVerifier` / `OAuthProxy` / `RemoteAuthProvider` for that.

fastmcp-guard *composes* with them. The `manage_auth` flag controls whether it
touches authentication:

```python
from fastmcp import FastMCP
from fastmcp_guard import Guard, RateLimit, AuditLog

mcp = FastMCP("my-server", auth=JWTVerifier(...))   # your OAuth/JWT

Guard(
    mcp,
    rate_limit=RateLimit(per_key="100/minute"),
    audit=AuditLog(backend="file", path="audit.jsonl"),
    manage_auth=False,   # add ops controls, keep your auth
)
```

- `manage_auth=None` (default): install the API-key verifier **only if** the
  server has no auth yet — an existing OAuth/JWT setup is preserved.
- `manage_auth=False`: never touch auth (ops middleware only).
- `manage_auth=True`: force API-key auth.

The audit and rate-limit features attribute calls to whatever access token your
auth produces, so they work the same on OAuth as on API keys.

---

## 9. CLI

The `keys` commands persist to a SQLite key store (`--db`, default
`fastmcp-guard-keys.db`):

```bash
fastmcp-guard keys create --name alice --scopes read:data,write:data
fastmcp-guard keys create --name ci --expires 90 --db ./keys.db
fastmcp-guard keys list [--all]           # --all includes revoked
fastmcp-guard keys rotate <key-id> --grace 24
fastmcp-guard keys revoke <key-id> [--force]

# Show recent audit entries (SQLite audit backend)
fastmcp-guard audit tail --db audit.db -n 20
```

> Use the `fmg_key_...` **id** (from `keys list`), not the token, for
> rotate/revoke. `audit query/export` and `rate` controls are on the roadmap.

To use `audit tail`, your server's `AuditLog` must use the **sqlite** backend
pointed at the same `--db` file.

---

## 10. Backends & persistence

| Concern | Options today | Notes |
|---------|---------------|-------|
| Key store | `memory`, `sqlite` | `memory` is dev-only (lost on restart). `sqlite` persists and survives restarts. `postgres`/`redis` raise `NotImplementedError`. |
| Rate limiting | in-process | Per-process only; not shared across workers yet (Redis planned). |
| Audit | `file`, `sqlite`, `http` | Writes are moved off the event loop. |

```python
# Keys persist across process restarts with sqlite:
s = KeyStore(backend="sqlite", path="keys.db")
```

---

## 11. Production checklist

- ✅ Use `KeyStore(backend="sqlite", ...)` (or wait for Postgres/Redis for
  multi-server). `memory` loses all keys on restart.
- ✅ Serve over HTTP so IP policy and `client_ip` in audit records work.
- ✅ Set `log_inputs=False` / `log_outputs=False` if tool args/outputs can
  contain secrets or PII.
- ✅ Rotate keys on a schedule with a grace window; revoke on suspected leak.
- ⚠️ Rate limiting is per-process. If you run multiple workers, each has its own
  window (a single worker, or the future Redis backend, gives a global limit).
- ⚠️ This is beta software (v0.2). It's tested end-to-end but young — pin the
  version and test in your own harness.

---

## 12. Verifying your setup

A quick end-to-end check using FastMCP's in-memory client:

```python
import asyncio, json, pathlib
from fastmcp import FastMCP, Client
from fastmcp_guard import Guard, AuditLog

mcp = FastMCP("check")

@mcp.tool
def hello(name: str) -> str:
    return f"hi {name}"

Guard(mcp, audit=AuditLog(backend="file", path="check.jsonl"))

async def main():
    async with Client(mcp) as c:
        print((await c.call_tool("hello", {"name": "you"})).data)
    print("audit:", pathlib.Path("check.jsonl").read_text().strip())

asyncio.run(main())
```

For a full HTTP example (auth, IP policy, audit identity), see
`tests/test_http_integration.py`.

---

## Links

- Source & issues: https://github.com/rohanprichard/fastmcp-guard
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Fixed-issues history: [BUGS.md](BUGS.md)
