# Backends

Both the key store and rate limiter support multiple storage backends.

## Key store backends

### Memory (default)

```python
KeyStore(backend="memory")
```

In-process dictionary. No dependencies, no persistence. **For dev and testing only** — all keys are lost on restart.

### SQLite

```python
KeyStore(backend="sqlite", path="keys.db")
```

Persistent local database. Zero configuration, no server needed. Good for single-server production deployments.

### PostgreSQL

```bash
pip install fastmcp-guard[postgres]
```

```python
KeyStore(backend="postgres", dsn="postgresql://user:pass@localhost:5432/mydb")
```

For multi-server HA deployments. Keys are shared across all server instances. Supports connection pooling via asyncpg.

### Redis

```bash
pip install fastmcp-guard[redis]
```

```python
KeyStore(backend="redis", dsn="redis://localhost:6379/0")
```

High-throughput key lookups. Can be combined with Redis rate limiting for a single Redis instance handling both.

---

## Rate limit backends

### Memory (default)

```python
RateLimit(per_key="100/minute", backend="memory")
```

Per-process sliding window. Works for single-server deployments. Each process has its own counters — not suitable for multi-server without sticky routing.

### Redis

```bash
pip install fastmcp-guard[redis]
```

```python
RateLimit(per_key="100/minute", backend="redis")
```

Distributed sliding window using Redis sorted sets. Counters are shared across all server instances — the limit is truly global.

---

## Audit backends

### File (JSONL)

```python
AuditLog(backend=FileBackend("audit.jsonl"))
```

Append-only JSONL. Trivial to tail and pipe to log aggregators.

### SQLite

```python
AuditLog(backend="sqlite", path="audit.db")
```

Queryable via `fastmcp-guard audit query` or `AuditLog.query()`. Recommended for most single-server setups.

### HTTP

```python
AuditLog(backend=HttpBackend("https://logs.example.com/ingest"))
```

POST each record to a webhook. Compatible with Loki, Datadog, Splunk, custom SIEMs.

### OpenTelemetry

```bash
pip install fastmcp-guard[otel]
```

```python
AuditLog(backend="otel")
```

Emits an OTel span per tool call. Works with any OTel-compatible backend (Jaeger, Tempo, Honeycomb, Datadog APM).

---

## Choosing the right backend

| Scale | Keys | Rate Limiting | Audit |
|-------|------|---------------|-------|
| Dev | `memory` | `memory` | `file` |
| Single server | `sqlite` | `memory` | `sqlite` |
| Multi-server | `postgres` or `redis` | `redis` | `http` or `otel` |
| High-throughput | `redis` | `redis` | `otel` |
