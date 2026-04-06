# CLI Reference

`fastmcp-guard` ships a CLI for managing keys and inspecting audit logs without writing code.

## Keys

### `fastmcp-guard keys create`

```
Usage: fastmcp-guard keys create [OPTIONS]

Options:
  --name, -n TEXT      Key label (required)
  --scopes, -s TEXT    Comma-separated scopes [default: none]
  --expires INT        Expiry in days from now [optional]
  --db TEXT            SQLite DB path [default: fastmcp-guard-keys.db]
```

```bash
fastmcp-guard keys create --name alice --scopes read:data,write:data
fastmcp-guard keys create --name ci-bot --scopes read:data --expires 30
```

### `fastmcp-guard keys list`

```
Usage: fastmcp-guard keys list [OPTIONS]

Options:
  --all        Include revoked keys
  --db TEXT    SQLite DB path
```

```bash
fastmcp-guard keys list
fastmcp-guard keys list --all
```

### `fastmcp-guard keys rotate`

```
Usage: fastmcp-guard keys rotate KEY_ID [OPTIONS]

Arguments:
  KEY_ID    ID of the key to rotate (required)

Options:
  --grace INT    Grace period in hours [default: 24]
  --db TEXT      SQLite DB path
```

```bash
fastmcp-guard keys rotate fmg_key_abc123
fastmcp-guard keys rotate fmg_key_abc123 --grace 0  # immediate
```

### `fastmcp-guard keys revoke`

```
Usage: fastmcp-guard keys revoke KEY_ID [OPTIONS]

Arguments:
  KEY_ID    ID of the key to revoke (required)

Options:
  --force, -f    Skip confirmation prompt
  --db TEXT      SQLite DB path
```

```bash
fastmcp-guard keys revoke fmg_key_abc123
fastmcp-guard keys revoke fmg_key_abc123 --force
```

---

## Audit

### `fastmcp-guard audit tail`

```
Usage: fastmcp-guard audit tail [OPTIONS]

Options:
  --lines, -n INT    Number of recent records [default: 20]
  --db TEXT          SQLite DB path
```

```bash
fastmcp-guard audit tail
fastmcp-guard audit tail --lines 50
```

### `fastmcp-guard audit query`

```
Usage: fastmcp-guard audit query [OPTIONS]

Options:
  --key TEXT      Filter by key name
  --tool TEXT     Filter by tool name
  --since TEXT    Time range: 1h, 24h, 7d
  --db TEXT       SQLite DB path
```

```bash
fastmcp-guard audit query --key alice
fastmcp-guard audit query --tool get_data --since 1h
fastmcp-guard audit query --key alice --tool get_data --since 24h
```

### `fastmcp-guard audit export`

```
Usage: fastmcp-guard audit export [OPTIONS]

Options:
  --format TEXT    Output format: jsonl, csv [default: jsonl]
  --since TEXT     Time range [optional]
  --out TEXT       Output file [default: stdout]
  --db TEXT        SQLite DB path
```

```bash
fastmcp-guard audit export --format csv --out audit.csv
fastmcp-guard audit export --since 7d --format jsonl --out last-week.jsonl
```

---

## Rate

### `fastmcp-guard rate status`

Show rate limit status. (Requires a running Guard instance for live data.)

### `fastmcp-guard rate reset`

```
Usage: fastmcp-guard rate reset KEY_ID

Arguments:
  KEY_ID    Key ID to reset rate limit for
```

```bash
fastmcp-guard rate reset fmg_key_abc123
```
