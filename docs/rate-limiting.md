# Rate Limiting

`fastmcp-guard` uses a **sliding window** algorithm for rate limiting — no bursty resets at the top of the minute.

## Basic usage

```python
from fastmcp_guard.rate import RateLimit

guard = Guard(
    mcp,
    rate_limit=RateLimit(
        per_key="100/minute",       # per API key
        global_limit="1000/minute", # across all keys combined
    ),
)
```

Rate strings accept: `second`, `minute`, `hour`, `day`.

```python
RateLimit(per_key="10/second")
RateLimit(per_key="500/hour")
RateLimit(per_key="5000/day")
```

## Per-tool limits {#per-tool}

Apply a tighter limit to expensive tools on top of the Guard-level limit:

```python
from fastmcp_guard.rate import rate_limit

@mcp.tool
@rate_limit("5/minute")  # only 5 calls/min to this tool, regardless of per-key limit
def run_expensive_analysis(data: str) -> str:
    ...
```

Both limits must pass — the per-tool limit is additional, not a replacement.

## Checking status programmatically

```python
status = guard._rate_limit.status(key_id="fmg_key_abc")
# {
#   "per_key": {"limit": 100, "used": 47, "remaining": 53, "window_seconds": 60},
#   "global":  {"limit": 1000, "used": 312, "remaining": 688, "window_seconds": 60}
# }
```

## Rate limit headers

When a request is rate limited, the server returns:

```
HTTP 429 Too Many Requests
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1741530060
Retry-After: 23
```

## Distributed rate limiting

For multi-server deployments, use the Redis backend so limits are shared across instances:

```python
from fastmcp_guard.rate import RateLimit

guard = Guard(
    mcp,
    rate_limit=RateLimit(
        per_key="100/minute",
        backend="redis",  # requires fastmcp-guard[redis]
    ),
    keys=KeyStore(backend="redis", dsn="redis://localhost:6379"),
)
```

## Resetting limits (ops / support)

```python
guard._rate_limit.reset("fmg_key_abc")
```

```bash
fastmcp-guard rate reset fmg_key_abc
```
