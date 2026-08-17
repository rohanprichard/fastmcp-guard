# fastmcp-guard 🛡️

> Production operations for [FastMCP](https://github.com/jlowin/fastmcp) servers: API-key lifecycle management, identity-aware audit logs, and policy controls without changing tool code.

[![PyPI](https://img.shields.io/pypi/v/fastmcp-guard)](https://pypi.org/project/fastmcp-guard/)
[![Python](https://img.shields.io/pypi/pyversions/fastmcp-guard)](https://pypi.org/project/fastmcp-guard/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Status

**Beta, v0.2.** The package is tested for single-server deployments. Memory and SQLite key stores, API-key issue/rotate/revoke flows, per-key/global/per-tool rate limits, audit logs, IP allow/deny rules, and the CLI are implemented. Postgres/Redis backends, distributed rate limiting, and OpenTelemetry export are planned.

## Install

```bash
pip install fastmcp-guard
```

## Quickstart

```python
from fastmcp import FastMCP
from fastmcp_guard import Guard

mcp = FastMCP("my-server")
guard = Guard(mcp)

key = guard.keys.create(name="alice", scopes=["read:data"])
print(key.token)  # show this once and store it safely

@mcp.tool
def get_data(query: str) -> str:
    return f"Results for: {query}"
```

Clients send the key as `Authorization: Bearer fmg_sk_...`.

## What it adds to FastMCP

FastMCP already provides strong authentication primitives and middleware. `fastmcp-guard` focuses on the operational layer around them:

- issue, inspect, rotate, and revoke scoped API keys
- enforce global, per-key, and per-tool limits
- record structured audit events by caller identity
- allow or deny callers by IP address when the transport provides one
- operate those controls through a CLI

## Documentation

- [Quickstart](docs/quickstart.md)
- [API keys](docs/keys.md)
- [Rate limiting](docs/rate-limiting.md)
- [Audit logging](docs/audit.md)
- [IP policy](docs/ip-policy.md)
- [CLI reference](docs/cli.md)
- [Backend choices](docs/backends.md)

## Local development

Requires Python 3.10+. Install the development extras, then run the repository test suite and static checks defined in `pyproject.toml`.

```bash
pip install -e '.[dev]'
pytest
ruff check .
mypy src
```

## License

MIT
