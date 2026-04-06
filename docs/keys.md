# API Key Management

API keys are the primary auth mechanism in `fastmcp-guard`. Each key has a name, a set of scopes, and a status lifecycle: `active` → `rotating` → `revoked`.

## Creating keys

```python
key = guard.keys.create(
    name="alice",
    scopes=["read:data", "write:data"],
    expires_in_days=90,        # optional
    metadata={"team": "eng"},  # optional arbitrary metadata
)
print(key.token)  # fmg_sk_...  SHOWN ONCE
print(key.id)     # fmg_key_abc123
```

Via CLI:

```bash
fastmcp-guard keys create \
  --name alice \
  --scopes read:data,write:data \
  --expires 90
```

## Listing keys

```python
keys = guard.keys.list()
for k in keys:
    print(k.id, k.name, k.scopes, k.status)
```

```bash
fastmcp-guard keys list
fastmcp-guard keys list --all  # include revoked
```

## Rotating keys

Rotation creates a new key while keeping the old one valid for a grace period. This lets you hand the new token to the caller without any downtime.

```python
new_key = guard.keys.rotate(
    key_id="fmg_key_abc123",
    grace_period_hours=24,  # default: 24h
)
print(new_key.token)  # new fmg_sk_... token
```

```bash
fastmcp-guard keys rotate fmg_key_abc123 --grace 24
```

During the grace period, the old key has status `rotating` and still authenticates. After `grace_period_hours`, it's automatically marked `revoked`.

## Revoking keys

```python
guard.keys.revoke("fmg_key_abc123")
```

```bash
fastmcp-guard keys revoke fmg_key_abc123
# --force to skip confirmation prompt
fastmcp-guard keys revoke fmg_key_abc123 --force
```

Revocation is immediate and permanent. The key will no longer authenticate.

## Scopes

Scopes are arbitrary strings. `fastmcp-guard` doesn't enforce a naming convention, but we recommend `resource:action` (e.g. `files:read`, `data:write`).

Scopes flow through to FastMCP's `AuthContext`, so you can use `require_scopes` from FastMCP on individual tools:

```python
from fastmcp.server.auth import require_scopes

@mcp.tool(auth=require_scopes("admin"))
def delete_all(): ...
```

Or check them yourself:

```python
from fastmcp.server.context import get_context

@mcp.tool
def sensitive_op():
    ctx = get_context()
    if "admin" not in (ctx.auth_token.scopes or []):
        raise PermissionError("admin scope required")
    ...
```

## Key expiry {#expiry}

Keys can have a fixed expiry date:

```python
# Expires in 30 days
key = guard.keys.create(name="temp-access", expires_in_days=30)
```

Expired keys fail verification with the same error as revoked keys — callers cannot distinguish expiry from revocation (by design).

## Token format

All tokens use the prefix `fmg_sk_` followed by 43 URL-safe base64 characters (32 random bytes). This makes them easy to grep for in logs and config files, and impossible to confuse with JWTs or other token formats.

```
fmg_sk_Ry8x2K_vD9mNpLqT3hWjYsAeUiObXcFzGkV4n...
```

Tokens are stored as bcrypt hashes — the plaintext is never persisted.
