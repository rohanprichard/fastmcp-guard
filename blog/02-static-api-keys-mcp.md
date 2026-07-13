---
title: "Static API keys don't have to be a liability — securing MCP servers that aren't ready for OAuth"
description: "Most authenticated MCP servers still run on static API keys. Here's how to make that safe: rotation, revocation, scopes, and an audit trail — without standing up an OAuth stack."
tags: [mcp, security, api-keys, fastmcp]
---

# Static API keys don't have to be a liability

The MCP ecosystem grew faster than its security did. Independent scans of public
MCP servers in early 2026 paint a rough picture: a large share require **no
authentication at all**, and among the ones that *do* authenticate, the majority
rely on **static API keys** — with only a small fraction using OAuth. (See
BlueRock Security's 2026 analysis, summarized in
[TrueFoundry's roundup of MCP security tools](https://www.truefoundry.com/blog/best-mcp-security-tools)
and other 2026 reviews.)

The usual reaction is "everyone should just move to OAuth." And for
internet-facing servers, the [MCP authorization spec](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
agrees: your server should be an OAuth 2.1 resource server validating
externally-issued tokens. Frameworks like [FastMCP](https://github.com/jlowin/fastmcp)
make that path genuinely easy.

But "just use OAuth" ignores a large middle ground:

- Internal tools and service-to-service calls where there's no human to consent.
- CI bots, cron jobs, and scripts that need a credential, not a login flow.
- Early-stage servers where standing up an IdP is premature.

For all of these, an API key is the right primitive. The problem was never the
key — it's that most key setups are **static and unmanaged**: one hard-coded
secret, no rotation, no revocation, no record of who used it.

## What makes an API key safe

A static key becomes an acceptable credential the moment you add four things:

1. **Rotation with a grace period.** You can issue a replacement, let the old
   key keep working for a bounded window, and then retire it automatically —
   without a coordinated downtime.
2. **Instant revocation.** A leaked key is a click, not a redeploy.
3. **Scopes.** A read-only key can't call your mutation tools.
4. **An audit trail keyed to identity.** When something goes wrong, you can
   answer "which key did this, and when?"

None of this requires OAuth. It requires *key management*.

## Doing it in FastMCP

This is the gap [`fastmcp-guard`](https://github.com/rohanprichard/fastmcp-guard)
fills. It wraps a FastMCP server and adds the management layer around API keys —
no changes to your tools:

```python
from fastmcp import FastMCP
from fastmcp_guard import Guard, KeyStore, AuditLog

mcp = FastMCP("internal-tools")
guard = Guard(
    mcp,
    keys=KeyStore(backend="sqlite", path="keys.db"),
    audit=AuditLog(backend="file", path="audit.jsonl"),
)

# Issue a scoped key for a CI bot
ci_key = guard.keys.create(name="ci-bot", scopes=["read:builds"])

# 90 days later, rotate it — old key stays valid for the grace window
new_key = guard.keys.rotate(ci_key.id, grace_period_hours=48)

# Leak? Kill it now.
guard.keys.revoke(new_key.id)
```

Under the hood, tokens are hashed with bcrypt (never stored in plaintext) and
verified in O(1) via a public selector, so a server with thousands of keys
doesn't turn every auth check into a linear bcrypt scan — a real DoS-amplification
trap in naive implementations.

## Keys and OAuth aren't either/or

The most useful framing isn't "keys vs OAuth" — it's layers. Authentication
(however you do it) establishes *identity*. On top of that you still want
*operational* controls: rate limiting so one client can't exhaust a tool, IP
allowlisting for internal deployments, and that audit trail. Those apply
regardless of how the caller authenticated.

`fastmcp-guard`'s middleware reads identity from whatever access token FastMCP
produces, so the same audit and rate-limiting controls work whether you're on
API keys today or OAuth tomorrow:

```python
mcp = FastMCP("my-server", auth=JWTVerifier(...))   # OAuth/JWT
Guard(mcp, rate_limit=RateLimit(per_key="100/minute"),
      audit=AuditLog(backend="file", path="audit.jsonl"),
      manage_auth=False)                             # keep your auth
```

## The takeaway

If your MCP server is one of the many still running on a static key, you don't
have to choose between "insecure" and "rebuild everything on OAuth." Add
rotation, revocation, scopes, and an audit trail, and a static key becomes a
managed credential you can actually stand behind.

```bash
pip install fastmcp-guard
```

MIT-licensed, on [GitHub](https://github.com/rohanprichard/fastmcp-guard).
