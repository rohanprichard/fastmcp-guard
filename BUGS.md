# Resolved issues

An independent review of the initial v0.1 scaffold found 10 correctness and
security issues — at the time, most advertised features were non-functional.

**All 10 are fixed as of v0.2 and covered by tests.** The behavior is exercised
end-to-end over both the in-memory client and a real HTTP server in
`tests/test_store_backends.py`, `tests/test_middleware.py`,
`tests/test_verifier.py`, and `tests/test_http_integration.py`.

| ID | Severity | Original issue | Resolution |
|----|----------|----------------|------------|
| BUG-001 | Critical | SQLite/Postgres/Redis key backends unimplemented (crashed) | Implemented `SQLiteKeyBackend`; `postgres`/`redis` raise a clear `NotImplementedError` |
| BUG-002 | Critical | Audit logging never wrote records | `GuardMiddleware.on_call_tool` writes an `AuditRecord` per call |
| BUG-003 | Critical | IP policy never enforced | Middleware checks the client IP from the HTTP request |
| BUG-004 | High | `@rate_limit` decorator was a no-op | Middleware reads the marker and enforces a per-(key, tool) limit |
| BUG-005 | High | Rotating keys never expired | Rotating keys past their grace period are revoked lazily on `verify` |
| BUG-006 | Security | O(n) bcrypt scan (DoS amplification) | Public token *selector* → O(1) lookup + a single bcrypt check |
| BUG-007 | Security | Rate-limiter check+record race | `asyncio.Lock` makes check+record atomic |
| BUG-008 | Bug | Decorator broke sync tools | Decorator branches on `iscoroutinefunction` |
| BUG-009 | Bug | Sync audit I/O blocked the event loop | File/SQLite audit writes use `asyncio.to_thread` |
| BUG-010 | Bug | `bcrypt` missing from dependencies | Added `bcrypt>=4.0` |

## Additional hardening since the review

- **v0.2.1** — Authentication no longer blocks the event loop: `verify_token`
  offloads the blocking key lookup + bcrypt check to a worker thread. The SQLite
  backends no longer leak connections (wrapped in `contextlib.closing`).

For full details of any change, see `CHANGELOG.md` and the git history.
