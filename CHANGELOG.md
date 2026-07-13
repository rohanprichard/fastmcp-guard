# Changelog

## 0.2.1

### Changed
- **Authentication no longer blocks the event loop.** `verify_token` runs the
  blocking key lookup + bcrypt comparison in a worker thread
  (`asyncio.to_thread`). bcrypt releases the GIL, so concurrent verifications
  run in parallel instead of serializing the server.
- Version is single-sourced from `__init__.py` (hatch dynamic version).

### Fixed
- SQLite backends leaked connections — `with sqlite3.connect(...)` commits but
  does not close. Connections are now wrapped in `contextlib.closing`.

### Internal
- `mypy --strict` now passes across the package; CI runs ruff + mypy + pytest.
- Added a PyPI publishing workflow (Trusted Publishing / OIDC) and `RELEASING.md`.
- Added a runnable server/client demo under `examples/demo/`; removed the
  outdated walkthrough POC.

## 0.2.0

First functional release. Every feature is now wired into the request path and
covered by tests (including end-to-end tests over a real HTTP server).

### Added
- **SQLite key backend** — persistent, single-server key storage with a unique
  `selector` index. Pluggable `KeyBackend` protocol (`memory`, `sqlite`).
- **GuardMiddleware** — a FastMCP `Middleware` that enforces IP policy, per-key
  and per-tool rate limits, and writes an audit record for every tool call.
- **O(1) verification** — tokens now carry a public `selector` (`fmg_sk_<selector>.<secret>`),
  so `verify()` does one indexed lookup and a single bcrypt check.
- CI workflow (ruff + pytest on Python 3.10–3.12) and a CHANGELOG.

### Fixed (see `BUGS.md`)
- Audit logging now actually writes records (was never wired). *(BUG-002)*
- IP allow/deny policy is now enforced on requests. *(BUG-003)*
- `@rate_limit` decorator is now enforced per (key, tool) and works with sync
  tools. *(BUG-004, BUG-008)*
- Rotating keys past their grace period are revoked lazily on verify. *(BUG-005)*
- Removed O(n) bcrypt scan (DoS amplification) via the selector index. *(BUG-006)*
- Rate-limiter check+record is now atomic under an `asyncio.Lock`. *(BUG-007)*
- File/SQLite audit writes moved off the event loop with `asyncio.to_thread`. *(BUG-009)*
- Added the missing `bcrypt` dependency. *(BUG-010)*

### Changed
- `KeyStoreVerifier` is now a proper `TokenVerifier` subclass and returns `None`
  on failure (instead of raising); it handles authentication only.
- Unimplemented key backends (`postgres`, `redis`) raise a clear
  `NotImplementedError` instead of `ModuleNotFoundError`.
- Development status promoted to Beta; version 0.1.0 → 0.2.0.
