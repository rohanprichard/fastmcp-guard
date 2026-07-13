# fastmcp-guard 🛡️

> Production operations layer for [FastMCP](https://github.com/jlowin/fastmcp) servers.
> API key management, rate limiting, and audit logging — without touching your tool code.

[![PyPI](https://img.shields.io/pypi/v/fastmcp-guard)](https://pypi.org/project/fastmcp-guard/)
[![Python](https://img.shields.io/pypi/pyversions/fastmcp-guard)](https://pypi.org/project/fastmcp-guard/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Project status — beta (v0.2)

fastmcp-guard is functional and covered by tests, including end-to-end tests
that boot a real HTTP server and exercise the full request path. It's suitable
for single-server deployments; multi-server backends are on the roadmap.

| Capability | Status |
|------------|--------|
| API key create / list / rotate / revoke | ✅ Working |
| Key store backends: `memory`, `sqlite` | ✅ Working |
| Authentication (Bearer token → identity) | ✅ Working |
| Per-key & global rate limiting | ✅ Working |
| Per-tool `@rate_limit` decorator | ✅ Working |
| Audit logging (`file`, `sqlite`, `http` backends) | ✅ Working |
| IP allowlist / denylist enforcement | ✅ Working |
| CLI (`keys create/list/rotate/revoke`, `audit tail`) | ✅ Working |
| Postgres / Redis key backends, OTel audit export | 🚧 Planned |
| Distributed (multi-process) rate limiting | 🚧 Planned (Redis) |

Verification is O(1): each token carries a public *selector* used to fetch a
single candidate key, checked with one bcrypt comparison. See [`BUGS.md`](BUGS.md)
for the (now-resolved) history of issues found during review.

---

## Why?

FastMCP ships with solid auth primitives — `JWTVerifier`, `OAuthProxy`, `require_scopes`. But once your MCP server hits production, you need more:

- **Who has access?** Issue, rotate, and revoke API keys without touching code.
- **Who's calling what?** Structured audit logs of every tool call, by identity.
- **Is someone hammering it?** Per-key rate limiting that just works.

`fastmcp-guard` is the ops layer FastMCP doesn't ship with. It wraps cleanly around your existing server — zero changes to your tools.

---

## Install

```bash
pip install fastmcp-guard
```

Optional extras (🚧 reserved for upcoming backends — not functional in v0.1):

```bash
pip install fastmcp-guard[postgres]   # PostgreSQL key store (planned)
pip install fastmcp-guard[redis]      # Redis rate limiting + key store (planned)
pip install fastmcp-guard[otel]       # OpenTelemetry audit export (planned)
```

---

## Quickstart

```python
from fastmcp import FastMCP
from fastmcp_guard import Guard

mcp = FastMCP("my-server")

guard = Guard(mcp)

# Issue API keys (programmatic or via CLI)
key = guard.keys.create(name="alice", scopes=["read:data", "write:data"])
print(key.token)  # fmg_sk_...

@mcp.tool
def get_data(query: str) -> str:
    return f"Results for: {query}"
```

```bash
# Or use the CLI (persists to a SQLite key store)
fastmcp-guard keys create --name alice --scopes read:data,write:data
fastmcp-guard keys list
fastmcp-guard keys rotate <key-id>
fastmcp-guard keys revoke <key-id>
```

Callers pass their key as a Bearer token:

```
Authorization: Bearer fmg_sk_abc123...
```

---

## Features

### 🔑 API Key Management

The `memory` (dev) and `sqlite` (persistent, single-server) backends are
available today; `postgres`/`redis` are planned.

```python
from fastmcp_guard import Guard
from fastmcp_guard.keys import KeyStore

guard = Guard(
    mcp,
    keys=KeyStore(backend="sqlite", path="keys.db"),
)

# Create keys with scopes
key = guard.keys.create(name="alice", scopes=["read:data"])

# Rotate (old key stays valid for 24h grace period by default)
new_key = guard.keys.rotate(key.id, grace_period_hours=24)

# Revoke immediately
guard.keys.revoke(key.id)

# Inspect
keys = guard.keys.list()
```

### ⏱️ Rate Limiting

```python
from fastmcp_guard.rate import RateLimit

guard = Guard(
    mcp,
    rate_limit=RateLimit(
        per_key="100/minute",
        global_limit="1000/minute",
    ),
)
```

Per-tool overrides — enforced per (key, tool) on top of the per-key limit:

```python
from fastmcp_guard.rate import rate_limit

@mcp.tool
@rate_limit("10/minute")  # tighter limit for expensive tools
def run_expensive_analysis(data: str) -> str: ...
```

### 📋 Audit Logging

A structured record is written for every tool call, attributed to the calling
key, with timing and status (`ok` / `error` / `rate_limited` / `unauthorized`).

```python
from fastmcp_guard.audit import AuditLog, FileBackend

guard = Guard(
    mcp,
    audit=AuditLog(
        backend=FileBackend("audit.jsonl"),
        # log_inputs=False,   # strip args from logs (PII)
        # log_outputs=False,  # strip outputs from logs
    ),
)
```

Every tool call is logged:

```json
{
  "ts": "2026-03-09T14:00:00Z",
  "key_id": "fmg_key_abc",
  "key_name": "alice",
  "tool": "get_data",
  "scopes": ["read:data"],
  "duration_ms": 42,
  "status": "ok"
}
```

Pluggable backends: `FileBackend`, `SQLiteBackend`, `HttpBackend`, `OTelBackend`.

### 🔒 IP Allowlisting

Enforced on each tool call when a client IP is available (HTTP transports).

```python
from fastmcp_guard.ip import IPPolicy

guard = Guard(
    mcp,
    ip=IPPolicy(
        allow=["10.0.0.0/8", "192.168.1.100"],
    ),
)
```

### 🧩 All together

```python
guard = Guard(
    mcp,
    keys=KeyStore(backend="sqlite", path="keys.db"),
    rate_limit=RateLimit(per_key="100/minute"),
    audit=AuditLog(backend=FileBackend("audit.jsonl")),
    ip=IPPolicy(allow=["10.0.0.0/8"]),
)
```

---

## CLI

The `keys` commands and `audit tail` are implemented and persist to SQLite.
`audit query/export` and `rate` controls are on the roadmap.

```bash
# Key management
fastmcp-guard keys create --name alice --scopes read:data,write:data
fastmcp-guard keys list
fastmcp-guard keys rotate <key-id>
fastmcp-guard keys revoke <key-id>
fastmcp-guard keys inspect <key-id>

# Audit log
fastmcp-guard audit tail              # live tail
fastmcp-guard audit query --key alice --tool get_data --since 1h
fastmcp-guard audit export --format csv --out audit.csv

# Rate limit status
fastmcp-guard rate status
fastmcp-guard rate reset <key-id>
```

---

## How it works

`fastmcp-guard` sits between FastMCP's transport and your tools. Authentication
uses FastMCP's native `TokenVerifier`; rate limiting, IP policy, and audit
logging run in a FastMCP `Middleware` — no monkey-patching, no transport hacks.

```
MCP Client
    │
    ▼
FastMCP transport (HTTP/SSE/stdio)
    │
    ▼
fastmcp-guard middleware
    ├── Token extraction → KeyStore lookup
    ├── Rate limit check
    ├── IP check
    └── Injects Identity into request context
    │
    ▼
FastMCP tool dispatcher
    │  ← @rate_limit per-tool decorators applied here
    ▼
Your tool function
    │
    ▼
fastmcp-guard response interceptor
    └── Audit log entry written
```

---

## Using with OAuth / JWT

fastmcp-guard is not an OAuth server, and it doesn't try to be — under the MCP
authorization spec your server is an OAuth 2.1 *resource server* that validates
externally-issued tokens, and FastMCP already ships `JWTVerifier`, `OAuthProxy`,
and `RemoteAuthProvider` for exactly that.

Instead, fastmcp-guard **composes** with whatever auth you use. Its audit, rate
limiting, and IP policy read identity from the access token FastMCP produces, so
they work on top of OAuth or JWT just as well as on top of API keys:

```python
mcp = FastMCP("my-server", auth=JWTVerifier(...))  # your existing OAuth/JWT

# Add ops controls without touching your auth:
Guard(mcp, rate_limit=RateLimit(per_key="100/minute"),
      audit=AuditLog(backend="file", path="audit.jsonl"),
      manage_auth=False)
```

By default (`manage_auth=None`) fastmcp-guard installs its API-key verifier only
if the server has no auth configured, so an existing OAuth setup is preserved.
Set `manage_auth=False` to be explicit, or `True` to force API-key auth.

---

## Key store backends

| Backend | Use case | Install | Status |
|---------|----------|---------|--------|
| `memory` | Dev/testing | built-in | ✅ Working |
| `sqlite` | Single-server production | built-in | ✅ Working |
| `postgres` | Multi-server, HA | `pip install fastmcp-guard[postgres]` | 🚧 Planned |
| `redis` | High-throughput, distributed rate limiting | `pip install fastmcp-guard[redis]` | 🚧 Planned |

---

## Audit log backends

| Backend | Use case | Install | Status |
|---------|----------|---------|--------|
| `file` | JSONL file, log rotation | built-in | ✅ Working |
| `sqlite` | Queryable local audit DB | built-in | ✅ Working |
| `http` | Webhook / SIEM integration | built-in | ✅ Working |
| `otel` | OpenTelemetry span export | `pip install fastmcp-guard[otel]` | 🚧 Planned |

---

## Comparison

> **Note:** As of FastMCP 2.9, FastMCP ships a native middleware pipeline with
> built-in `RateLimitingMiddleware`, `SlidingWindowRateLimitingMiddleware`,
> logging, timing, and error-handling middleware. fastmcp-guard does **not** aim
> to replace those — for basic rate limiting and logging, prefer FastMCP's
> built-ins. fastmcp-guard's niche is the part FastMCP does *not* ship:
> **API-key lifecycle management** (issue / rotate / revoke with scopes) plus an
> ops CLI and a batteries-included audit trail, all in-process without a gateway.

| Feature | FastMCP built-in | fastmcp-guard |
|---------|-----------------|---------------|
| JWT verification | ✅ `JWTVerifier` | uses it |
| OAuth2 / OIDC | ✅ `OAuthProxy` | uses it |
| Static tokens | ✅ `StaticTokenVerifier` | wraps it |
| Rate limiting | ✅ `RateLimitingMiddleware` (2.9+) | adds per-key limits |
| Logging middleware | ✅ `LoggingMiddleware` (2.9+) | — |
| **API key CRUD** | ❌ | ✅ |
| **Key rotation / revocation** | ❌ | ✅ |
| **Identity-aware audit logging** | ❌ (pattern only) | ✅ |
| **IP allowlisting** | ❌ | ✅ |
| **CLI for key ops** | ❌ | ✅ |

---

## Requirements

- Python ≥ 3.10
- FastMCP ≥ 2.0

---

## License

MIT
