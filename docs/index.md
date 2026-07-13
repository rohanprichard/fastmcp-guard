# fastmcp-guard

> Production operations layer for FastMCP servers.

!!! note "Beta (v0.2)"
    fastmcp-guard is functional and covered by tests, including end-to-end tests
    over a real HTTP server. **Working today:** API keys (memory + SQLite),
    Bearer-token auth, per-key/global/per-tool rate limiting, audit logging
    (`file`/`sqlite`/`http`), IP allow/deny enforcement, and the CLI.
    **Planned:** Postgres/Redis backends, OTel audit export, distributed rate
    limiting. Suitable for single-server deployments.

`fastmcp-guard` gives your [FastMCP](https://github.com/jlowin/fastmcp) server the operational tooling it needs to run in production:

- **API key management** — issue, rotate, and revoke keys without redeploying
- **Rate limiting** — per-key and global sliding-window limits
- **Audit logging** — structured record of every tool call, by identity
- **IP allowlisting** — restrict access by client IP

## Why not just use FastMCP's built-in auth?

FastMCP ships with solid auth *primitives* — `JWTVerifier`, `OAuthProxy`, `require_scopes` — and, since 2.9, a native middleware pipeline with built-in rate limiting and logging. These handle the *protocol* and *throttling* layers.

`fastmcp-guard` focuses on the *key-lifecycle and identity* layer that FastMCP does not ship:

| Question | FastMCP | fastmcp-guard |
|----------|---------|---------------|
| Is this JWT valid? | ✅ `JWTVerifier` | — |
| Is someone hammering the server? | ✅ `RateLimitingMiddleware` (2.9+) | adds per-key limits |
| Who has access? (issue/rotate/revoke keys) | ❌ | ✅ |
| How often is Alice calling `run_analysis`? | ❌ | 🚧 planned |
| Who called what, when, from where? | ❌ | 🚧 planned (audit) |

Think of FastMCP's auth as the lock; `fastmcp-guard` as the key management office.

## Install

```bash
pip install fastmcp-guard
```

## Quickstart

```python
from fastmcp import FastMCP
from fastmcp_guard import Guard

mcp = FastMCP("my-server")
guard = Guard(mcp)

# Issue a key
key = guard.keys.create(name="alice", scopes=["read:data"])
print(key.token)  # fmg_sk_... (shown once)

@mcp.tool
def get_data(query: str) -> str:
    return f"Results for: {query}"
```

Callers pass the token as a Bearer header:
```
Authorization: Bearer fmg_sk_...
```

## Next steps

- [Quickstart](quickstart.md) — get running in 5 minutes
- [API Keys](keys.md) — full key lifecycle guide
- [Rate Limiting](rate-limiting.md) — per-key and global limits
- [Audit Logging](audit.md) — structured audit records
- [IP Policy](ip-policy.md) — allowlist and denylist
- [CLI Reference](cli.md) — `fastmcp-guard` command
- [Backends](backends.md) — SQLite, Postgres, Redis
