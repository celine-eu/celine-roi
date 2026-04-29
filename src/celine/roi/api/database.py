"""Async Postgres persistence for estimates (asyncpg, no ORM)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import asyncpg

from celine.roi.settings import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Create the asyncpg connection pool from settings.database_url."""
    global _pool
    database_url = settings.database_url
    if not database_url:
        logger.info("database_url not set — estimate persistence disabled")
        return
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    _pool = await asyncpg.create_pool(
        url,
        min_size=settings.database_pool_min,
        max_size=settings.database_pool_max,
    )
    logger.info("asyncpg pool created")


async def close_pool() -> None:
    """Close the asyncpg pool if it was created."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("asyncpg pool closed")


def get_pool() -> asyncpg.Pool | None:
    """Return the pool (None when persistence is disabled)."""
    return _pool


async def save_estimate(
    *,
    pool: asyncpg.Pool,
    endpoint: str,
    status: str,
    request: dict[str, Any],
    response: dict[str, Any] | None,
    duration_ms: int,
    error_message: str | None = None,
) -> uuid.UUID:
    """INSERT one estimate row and return its UUID.

    Args:
        pool: asyncpg connection pool.
        endpoint: API endpoint name (e.g. "scenario", "compare").
        status: Outcome status ("success" or "error").
        request: Request payload dict to store as JSONB.
        response: Response payload dict to store as JSONB, or None on error.
        duration_ms: Request processing time in milliseconds.
        error_message: Human-readable error description when status is "error".

    Returns:
        UUID of the newly created estimate row.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO estimates (endpoint, status, request, response, error_message, duration_ms)
        VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6)
        RETURNING id
        """,
        endpoint,
        status,
        json.dumps(request),
        json.dumps(response) if response is not None else None,
        error_message,
        duration_ms,
    )
    return row["id"]


async def get_estimate(
    pool: asyncpg.Pool,
    estimate_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Fetch a single estimate by UUID. Returns None if not found.

    Args:
        pool: asyncpg connection pool.
        estimate_id: UUID of the estimate to retrieve.

    Returns:
        Dict with estimate fields, or None if no row matches the UUID.
    """
    row = await pool.fetchrow(
        "SELECT * FROM estimates WHERE id = $1",
        estimate_id,
    )
    if row is None:
        return None
    return _row_to_dict(row)


async def list_estimates(
    pool: asyncpg.Pool,
    *,
    limit: int = 20,
    offset: int = 0,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """Paginated estimate list, most recent first.

    Args:
        pool: asyncpg connection pool.
        limit: Maximum number of items to return.
        offset: Number of items to skip for pagination.
        endpoint: Optional filter to return only rows for a specific endpoint.

    Returns:
        Dict with keys: items (list), total (int), limit (int), offset (int).
    """
    if endpoint:
        total_row = await pool.fetchrow(
            "SELECT count(*) FROM estimates WHERE endpoint = $1",
            endpoint,
        )
        rows = await pool.fetch(
            """
            SELECT id, endpoint, status, duration_ms, created_at, response
            FROM estimates WHERE endpoint = $3
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
            endpoint,
        )
    else:
        total_row = await pool.fetchrow("SELECT count(*) FROM estimates")
        rows = await pool.fetch(
            """
            SELECT id, endpoint, status, duration_ms, created_at, response
            FROM estimates
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    items = []
    for row in rows:
        item: dict[str, Any] = {
            "id": row["id"],
            "endpoint": row["endpoint"],
            "status": row["status"],
            "duration_ms": row["duration_ms"],
            "created_at": row["created_at"].isoformat(),
        }
        if row["response"]:
            resp = json.loads(row["response"])
            item["summary"] = _extract_summary(resp, row["endpoint"])
        else:
            item["summary"] = None
        items.append(item)

    return {
        "items": items,
        "total": total_row["count"],
        "limit": limit,
        "offset": offset,
    }


def _extract_summary(response: dict[str, Any], endpoint: str) -> dict[str, Any]:
    """Extract a compact summary from stored response JSONB.

    Args:
        response: Full response dict parsed from JSONB.
        endpoint: API endpoint name used to select the extraction strategy.

    Returns:
        Dict with a compact summary appropriate for list views.
    """
    if endpoint == "scenario":
        return response.get("summary", {})
    if endpoint == "compare":
        return {
            "scenario_count": len(response.get("scenarios", {})),
            "scenario_names": list(response.get("scenarios", {}).keys()),
        }
    return {}


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    """Convert an asyncpg Record to a plain dict, deserializing JSONB.

    Args:
        row: asyncpg Record returned by fetchrow.

    Returns:
        Plain dict with JSONB fields deserialized and timestamps as ISO strings.
    """
    result: dict[str, Any] = dict(row)
    if result.get("request") is not None:
        result["request"] = json.loads(result["request"])
    if result.get("response") is not None:
        result["response"] = json.loads(result["response"])
    if result.get("created_at") is not None:
        result["created_at"] = result["created_at"].isoformat()
    return result
