"""Storing what an anonymous caller computed, within bounds (REQ-0403, REQ-1305)."""

from __future__ import annotations

import logging
from typing import Any

from celine.roi.api.database import get_pool, save_estimate
from celine.roi.api.limits import FixedWindowLimiter
from celine.roi.settings import settings

logger = logging.getLogger(__name__)

# One budget for the whole process: above it the caller still gets the result and
# nothing is stored, so a flood of anonymous calls cannot fill the database.
_writes = FixedWindowLimiter(settings.estimates_max_writes_per_minute)


def compact_response(endpoint: str, response: dict[str, Any]) -> dict[str, Any]:
    """What is kept of a response: its summary, never the hourly series.

    A full scenario response is ~650 KiB, nearly all of it 8760-value arrays the
    caller already received; the summary is what a reviewer reads.
    """
    if endpoint == "compare":
        return {
            "scenarios": {
                name: {"summary": result.get("summary")}
                for name, result in response.get("scenarios", {}).items()
            },
            "summary_table": response.get("summary_table"),
        }
    return {"summary": response.get("summary")}


async def persist_estimate(
    *,
    endpoint: str,
    status: str,
    request_body: dict,
    response_body: dict | None,
    duration_ms: int,
    client_ip: str | None,
    error_message: str | None = None,
) -> None:
    pool = get_pool()
    if pool is None:
        return
    _writes.limit = settings.estimates_max_writes_per_minute
    if _writes.hit("all") is not None:
        logger.warning(
            "Estimate not stored: over %d stored estimates per minute",
            _writes.limit,
        )
        return
    try:
        await save_estimate(
            pool=pool,
            endpoint=endpoint,
            status=status,
            request=request_body,
            response=compact_response(endpoint, response_body) if response_body else None,
            duration_ms=duration_ms,
            error_message=error_message,
            client_ip=client_ip,
        )
    except Exception:
        logger.exception("Failed to persist estimate")
