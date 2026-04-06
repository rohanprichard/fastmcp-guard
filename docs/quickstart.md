# Quickstart

Get a FastMCP server with API key auth, rate limiting, and audit logging in under 5 minutes.

## 1. Install

```bash
pip install fastmcp-guard
```

## 2. Create your server

```python
# server.py
from fastmcp import FastMCP
from fastmcp_guard import Guard
from fastmcp_guard.keys import KeyStore
from fastmcp_guard.rate import RateLimit
from fastmcp_guard.audit import AuditLog

mcp = FastMCP("my-server")

guard = Guard(
    mcp,
    keys=KeyStore(backend="sqlite", path="keys.db"),
    rate_limit=RateLimit(per_key="100/minute"),
    audit=AuditLog(backend="sqlite", path="audit.db"),
)

@mcp.tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Sunny in {city}, 22°C"

@mcp.tool
def list_files(directory: str) -> list[str]:
    """List files in a directory."""
    import os
    return os.listdir(directory)
```

## 3. Issue API keys

```bash
# Via CLI
fastmcp-guard keys create --name alice --scopes read:weather
fastmcp-guard keys create --name bob --scopes read:weather,read:files

# Or programmatically
python -c "
from fastmcp_guard.keys import KeyStore
store = KeyStore(backend='sqlite', path='keys.db')
key = store.create(name='alice', scopes=['read:weather'])
print(key.token)
"
```

> **Save the token now.** It's shown exactly once. If you lose it, rotate the key.

## 4. Run your server

```bash
fastmcp run server.py
```

## 5. Call a tool

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer fmg_sk_YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool": "get_weather", "args": {"city": "London"}}'
```

## 6. Check the audit log

```bash
fastmcp-guard audit tail --db audit.db
```

```
┌──────────────────────────────────────────────┐
│              Recent Audit Log                │
├─────────────────┬───────┬───────────┬────────┤
│ Time            │ Key   │ Tool      │ Status │
├─────────────────┼───────┼───────────┼────────┤
│ 2026-03-09 14:  │ alice │ get_weath │ ok     │
│ 2026-03-09 14:  │ bob   │ list_file │ ok     │
└─────────────────┴───────┴───────────┴────────┘
```

## What's next?

- Add [per-tool rate limits](rate-limiting.md#per-tool) for expensive tools
- Set up [key expiry](keys.md#expiry) for temporary access
- Configure [IP allowlisting](ip-policy.md) for internal-only servers
- Switch to [Postgres backend](backends.md#postgres) for multi-server deployments
