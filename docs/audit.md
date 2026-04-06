# Audit Logging

Every tool call is logged as a structured record: who called it, what tool, how long it took, and whether it succeeded.

## Basic setup

```python
from fastmcp_guard.audit import AuditLog

guard = Guard(
    mcp,
    audit=AuditLog(backend="sqlite", path="audit.db"),
)
```

## Record format

Each record is a JSON object:

```json
{
  "ts": "2026-03-09T14:00:00.123Z",
  "key_id": "fmg_key_abc123",
  "key_name": "alice",
  "tool": "get_data",
  "scopes": ["read:data"],
  "duration_ms": 42.1,
  "status": "ok",
  "error": null,
  "input_args": {"query": "sales 2026"},
  "output_preview": "Q1 revenue: $1.2M...",
  "client_ip": "10.0.1.5",
  "metadata": {"team": "eng"}
}
```

`status` is one of: `ok`, `error`, `rate_limited`, `unauthorized`.

## Backends

### File (JSONL)

```python
from fastmcp_guard.audit import AuditLog, FileBackend

audit = AuditLog(backend=FileBackend("audit.jsonl"))
```

One JSON record per line. Easy to tail, rotate, and pipe to log aggregators (`jq`, Loki, Datadog, etc.).

```bash
tail -f audit.jsonl | jq 'select(.status == "error")'
```

### SQLite (queryable)

```python
audit = AuditLog(backend="sqlite", path="audit.db")
```

```bash
fastmcp-guard audit tail --db audit.db
fastmcp-guard audit query --key alice --tool get_data --since 1h
```

Programmatic queries:

```python
records = await guard._audit.query(
    key_name="alice",
    tool="get_data",
    since=datetime.now(timezone.utc) - timedelta(hours=1),
    limit=50,
)
```

### HTTP / Webhook

```python
from fastmcp_guard.audit import AuditLog, HttpBackend

audit = AuditLog(
    backend=HttpBackend(
        url="https://logs.example.com/ingest",
        headers={"Authorization": "Bearer your-token"},
    )
)
```

Each record is POSTed as JSON. Failures are silently logged — audit errors never interrupt tool execution.

### OpenTelemetry

```bash
pip install fastmcp-guard[otel]
```

```python
audit = AuditLog(backend="otel")
```

Emits an OTel span per tool call with all record fields as span attributes. Works with Jaeger, Tempo, Honeycomb, Datadog APM, etc.

## Privacy controls

Strip inputs and/or outputs from audit records when they may contain PII:

```python
audit = AuditLog(
    backend="sqlite",
    log_inputs=False,   # don't log tool arguments
    log_outputs=False,  # don't log output previews
)
```

`ts`, `key_id`, `key_name`, `tool`, `scopes`, `duration_ms`, and `status` are always logged.

## Exporting

```bash
# Export last 7 days as CSV
fastmcp-guard audit export --since 7d --format csv --out audit.csv

# Export all as JSONL
fastmcp-guard audit export --format jsonl --out audit.jsonl
```
