# fastmcp-guard 🛡️

> Production operations layer for [FastMCP](https://github.com/jlowin/fastmcp) servers.
> API key management, rate limiting, and audit logging — without touching your tool code.

[![PyPI](https://img.shields.io/pypi/v/fastmcp-guard)](https://pypi.org/project/fastmcp-guard/)
[![Python](https://img.shields.io/pypi/pyversions/fastmcp-guard)](https://pypi.org/project/fastmcp-guard/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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

Optional extras:

```bash
pip install fastmcp-guard[postgres]   # PostgreSQL key store
pip install fastmcp-guard[redis]      # Redis rate limiting + key store
pip install fastmcp-guard[otel]       # OpenTelemetry audit export
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
# Or use the CLI
fastmcp-guard keys create --name alice --scopes read:data,write:data
fastmcp-guard keys list
fastmcp-guard keys rotate fmg_sk_abc123
fastmcp-guard keys revoke fmg_sk_abc123
```

Callers pass their key as a Bearer token:

```
Authorization: Bearer fmg_sk_abc123...
```

---

## Features

### 🔑 API Key Management

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

Per-tool overrides:

```python
from fastmcp_guard.rate import rate_limit

@mcp.tool
@rate_limit("10/minute")  # tighter limit for expensive tools
def run_expensive_analysis(data: str) -> str: ...
```

### 📋 Audit Logging

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

`fastmcp-guard` sits between FastMCP's transport and your tools. It uses FastMCP's native `TokenVerifier` and `AuthCheck` hooks — no monkey-patching, no transport hacks.

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

## Key store backends

| Backend | Use case | Install |
|---------|----------|---------|
| `memory` | Dev/testing | built-in |
| `sqlite` | Single-server production | built-in |
| `postgres` | Multi-server, HA | `pip install fastmcp-guard[postgres]` |
| `redis` | High-throughput, distributed rate limiting | `pip install fastmcp-guard[redis]` |

---

## Audit log backends

| Backend | Use case | Install |
|---------|----------|---------|
| `file` | JSONL file, log rotation | built-in |
| `sqlite` | Queryable local audit DB | built-in |
| `http` | Webhook / SIEM integration | built-in |
| `otel` | OpenTelemetry span export | `pip install fastmcp-guard[otel]` |

---

## Comparison

| Feature | FastMCP built-in | fastmcp-guard |
|---------|-----------------|---------------|
| JWT verification | ✅ `JWTVerifier` | uses it |
| OAuth2 / OIDC | ✅ `OAuthProxy` | uses it |
| Static tokens | ✅ `StaticTokenVerifier` | wraps it |
| **API key CRUD** | ❌ | ✅ |
| **Key rotation / revocation** | ❌ | ✅ |
| **Rate limiting** | ❌ | ✅ |
| **Audit logging** | ❌ | ✅ |
| **IP allowlisting** | ❌ | ✅ |
| **CLI for ops** | ❌ | ✅ |

---

## Requirements

- Python ≥ 3.10
- FastMCP ≥ 2.0

---

## License

MIT
