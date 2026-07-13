# fastmcp-guard demo

A minimal, runnable demonstration of protecting a FastMCP server with
fastmcp-guard: **API-key auth, per-tool rate limiting, audit logging, and IP
policy** — with no changes to the tool code.

## Files

| File | What it is |
|------|------------|
| `server.py` | A FastMCP HTTP server wrapped with `Guard`. Exposes three tools and provisions a demo API key on startup. |
| `client.py` | A FastMCP client that connects and walks through auth, rate limiting, and the audit trail. |

## Run it

From the repository root, in one terminal:

```bash
python examples/demo/server.py
```

It starts on `http://127.0.0.1:8000/mcp/`, prints the issued token, and writes
it to `examples/demo/.demo_token` so the client can pick it up.

In a second terminal:

```bash
python examples/demo/client.py
```

## What you'll see

```
1. Valid API key — authenticated calls succeed
   tools available: ['get_weather', 'echo', 'expensive_report']
   get_weather -> It's sunny in Lisbon, 22°C.

2. Invalid API key — rejected by the auth layer
   rejected as expected: HTTPStatusError

3. Per-tool rate limit — expensive_report is capped at 3/minute
   call 1: OK    -> Generated an expensive report on: q1
   call 2: OK
   call 3: OK
   call 4: BLOCKED (ToolError) — rate limited
   call 5: BLOCKED (ToolError) — rate limited

4. Audit log — every call was recorded (server side)
   - get_weather        key=demo-client  status=ok           ip=127.0.0.1
   - expensive_report   key=demo-client  status=rate_limited ip=127.0.0.1
   ...
```

The audit trail is written to `examples/demo/audit.jsonl` — inspect it directly:

```bash
cat examples/demo/audit.jsonl | python -m json.tool
```

## How it maps to the code

Everything is configured in `server.py` in a single `Guard(...)` call:

```python
guard = Guard(
    mcp,
    keys=KeyStore(backend="memory"),           # who has access
    rate_limit=RateLimit(per_key="20/minute"), # overall per-key ceiling
    audit=AuditLog(backend="file", path="audit.jsonl"),  # who called what
    ip=IPPolicy(allow=["127.0.0.0/8", "::1"]), # only localhost may connect
)
```

The tighter per-tool limit comes from a decorator on the tool itself:

```python
@mcp.tool
@rate_limit("3/minute")
def expensive_report(topic: str) -> str: ...
```

> **Note:** this demo writes the token to a file purely to hand it between two
> local processes. In production, issue keys with the CLI (`fastmcp-guard keys
> create`) or the programmatic API and deliver the token to the caller securely —
> never commit tokens to disk. See [`../../GUIDE.md`](../../GUIDE.md).
