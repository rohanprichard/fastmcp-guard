# IP Policy

Restrict which client IPs can access your MCP server.

## Allowlist

Only allow specific IPs or CIDR ranges:

```python
from fastmcp_guard.ip import IPPolicy

guard = Guard(
    mcp,
    ip=IPPolicy(allow=["10.0.0.0/8", "192.168.1.0/24"]),
)
```

## Denylist

Block specific IPs (everything else is allowed):

```python
guard = Guard(
    mcp,
    ip=IPPolicy(deny=["203.0.113.0/24"]),
)
```

## Combined

Allow a range but block a subnet within it:

```python
guard = Guard(
    mcp,
    ip=IPPolicy(
        allow=["10.0.0.0/8"],
        deny=["10.99.0.0/16"],  # blocked even though it's in the allow range
    ),
)
```

Deny is checked first — if an IP matches the denylist, it's blocked regardless of the allowlist.

## Checking programmatically

```python
policy = IPPolicy(allow=["10.0.0.0/8"])
assert policy.is_allowed("10.0.1.5") is True
assert policy.is_allowed("8.8.8.8") is False
```
