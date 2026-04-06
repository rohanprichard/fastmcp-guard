"""HTTP webhook audit backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp_guard.audit.log import AuditRecord


class HttpBackend:
    """POST audit records to an HTTP endpoint (webhook / SIEM).

    Each record is sent as a JSON POST. Failures are logged but
    never raise — audit logging must not break tool execution.

    Args:
        url: Endpoint to POST records to.
        headers: Additional headers (e.g. Authorization).
        timeout: Request timeout in seconds. Default 5.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout

    async def write(self, record: AuditRecord) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                await client.post(
                    self._url,
                    json=record.to_dict(),
                    headers={"Content-Type": "application/json", **self._headers},
                )
        except Exception as e:
            import logging
            logging.getLogger("fastmcp_guard.audit.http").warning(
                f"Failed to send audit record to {self._url}: {e}"
            )
