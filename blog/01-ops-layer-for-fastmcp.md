---
title: "Add API keys, audit logs, and rate limits to your FastMCP server in 10 lines"
description: "FastMCP gives you great auth primitives. fastmcp-guard adds the operational layer around them — key lifecycle, per-identity audit, and rate limiting — without touching your tools."
tags: [mcp, fastmcp, python, security]
---

# Add API keys, audit logs, and rate limits to your FastMCP server in 10 lines

[FastMCP](https://github.com/jlowin/fastmcp) is the fastest way to build an MCP
server in Python. Out of the box it gives you solid auth *primitives* —
`JWTVerifier`, `OAuthProxy`, `StaticTokenVerifier` — and, since 2.9, a native
middleware pipeline with rate limiting and logging.

But the day you put a server in front of real users, a different set of
questions shows up:

- **Who has access, and how do I turn it off?** You need to *issue* keys, and
  *rotate* or *revoke* them without redeploying.
- **Who called what, when?** You need an audit trail keyed to identity, not just
  request logs.
- **Is one client hammering an expensive tool?** You need per-identity and
  per-tool rate limits.

That's the operational layer, and it's what [`fastmcp-guard`](https://github.com/rohanprichard/fastmcp-guard)
adds — as a wrapper around your existing server, with zero changes to your tool
code.

## The 10-line version

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

key = guard.keys.create(name="alice", scopes=["read:data"])
print(key.token)  # fmg_sk_...  (shown once — store it)
```

Callers pass the token as a Bearer header. That's it — auth, rate limiting, and
an audit trail are now live.

## Key lifecycle that actually rotates

Long-lived static keys are a liability. `fastmcp-guard` makes rotation a
one-liner, with a grace period so you don't break live clients:

```python
new_key = guard.keys.rotate(old_key.id, grace_period_hours=24)
# old key keeps working for 24h; after that it's revoked automatically
guard.keys.revoke(new_key.id)  # or kill it immediately
```

Tokens are verified in O(1): each token carries a public *selector* used to
fetch a single candidate key, which is then checked with one bcrypt comparison —
so verification cost doesn't grow with the number of keys you've issued.

There's a CLI too:

```bash
fastmcp-guard keys create --name ci-bot --scopes read:data
fastmcp-guard keys list
fastmcp-guard keys rotate <key-id>
fastmcp-guard keys revoke <key-id>
```

## An audit trail keyed to identity

Every tool call produces a structured record — who, what, how long, and the
outcome (`ok` / `error` / `rate_limited` / `unauthorized`):

```json
{"ts": "2026-07-13T14:00:00Z", "key_name": "alice", "tool": "get_data",
 "scopes": ["read:data"], "duration_ms": 42, "status": "ok",
 "client_ip": "203.0.113.7"}
```

Backends include JSONL files, a queryable SQLite DB, and HTTP webhooks for your
SIEM. Redaction is opt-out at the source — set `log_inputs=False` to keep tool
arguments out of the log when they might contain PII.

## Per-tool rate limits

Global limits are blunt. Put a tighter ceiling on your expensive tools:

```python
from fastmcp_guard.rate import rate_limit

@mcp.tool
@rate_limit("10/minute")  # enforced per (key, tool)
def run_expensive_analysis(data: str) -> str:
    ...
```

## It composes with OAuth

Under the MCP authorization spec, your server is an OAuth 2.1 *resource server* —
it validates tokens issued by an external provider. FastMCP already does that.
`fastmcp-guard` doesn't replace it; the audit, rate-limit, and IP-policy
middleware read identity from whatever access token FastMCP produces:

```python
mcp = FastMCP("my-server", auth=JWTVerifier(...))   # your OAuth/JWT
Guard(mcp, audit=AuditLog(backend="file", path="audit.jsonl"),
      manage_auth=False)  # add ops controls, keep your auth
```

## Try it

```bash
pip install fastmcp-guard
```

It's MIT-licensed and on [GitHub](https://github.com/rohanprichard/fastmcp-guard).
Issues and PRs welcome — especially if you're running MCP servers in production
and hitting the operational gaps this is meant to fill.
