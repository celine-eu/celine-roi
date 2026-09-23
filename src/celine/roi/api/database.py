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


async def save_feedback(
    pool: asyncpg.Pool,
    *,
    community_key: str,
    user_id: str,
    rating: int,
    comment: str | None,
    context: dict[str, Any],
    screenshot_mime_type: str | None,
    screenshot_bytes: bytes | None,
    client_ip: str | None,
) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        INSERT INTO feedback_entries (
            community_key, user_id, rating, comment, page_url, page_title, page_path,
            locale, timezone, user_agent, viewport_width, viewport_height, screen_width,
            screen_height, color_scheme, client_timestamp, client_ip, extra_context,
            screenshot_mime_type, screenshot_bytes
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
            $15, $16, $17, $18::jsonb, $19, $20
        )
        RETURNING id, created_at
        """,
        community_key,
        user_id,
        rating,
        comment,
        context["page_url"],
        context.get("page_title"),
        context.get("page_path"),
        context.get("locale"),
        context.get("timezone"),
        context.get("user_agent"),
        context.get("viewport_width"),
        context.get("viewport_height"),
        context.get("screen_width"),
        context.get("screen_height"),
        context.get("color_scheme"),
        context.get("client_timestamp"),
        client_ip,
        json.dumps(context.get("extra") or {}),
        screenshot_mime_type,
        screenshot_bytes,
    )
    return dict(row)


async def list_feedback(
    pool: asyncpg.Pool,
    community_key: str,
    *,
    status: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    counts_rows = await pool.fetch(
        "SELECT status, count(*) AS count FROM feedback_entries "
        "WHERE community_key = $1 GROUP BY status",
        community_key,
    )
    counts = {row["status"]: row["count"] for row in counts_rows}
    if status:
        total = await pool.fetchval(
            "SELECT count(*) FROM feedback_entries WHERE community_key = $1 AND status = $2",
            community_key,
            status,
        )
        rows = await pool.fetch(
            """
            SELECT id, rating, comment, page_url, page_title, page_path, locale, timezone,
                   viewport_width, viewport_height, screen_width, screen_height, color_scheme,
                   client_timestamp, extra_context, screenshot_bytes IS NOT NULL AS has_screenshot,
                   status, seen_at, resolved_at, created_at
            FROM feedback_entries
            WHERE community_key = $1 AND status = $2
            ORDER BY created_at DESC, id DESC
            LIMIT $3 OFFSET $4
            """,
            community_key,
            status,
            page_size,
            (page - 1) * page_size,
        )
    else:
        total = await pool.fetchval(
            "SELECT count(*) FROM feedback_entries WHERE community_key = $1",
            community_key,
        )
        rows = await pool.fetch(
            """
            SELECT id, rating, comment, page_url, page_title, page_path, locale, timezone,
                   viewport_width, viewport_height, screen_width, screen_height, color_scheme,
                   client_timestamp, extra_context, screenshot_bytes IS NOT NULL AS has_screenshot,
                   status, seen_at, resolved_at, created_at
            FROM feedback_entries
            WHERE community_key = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2 OFFSET $3
            """,
            community_key,
            page_size,
            (page - 1) * page_size,
        )
    return {
        "community_key": community_key,
        "page": page,
        "page_size": page_size,
        "total": total or 0,
        "counts": {
            "new": counts.get("new", 0),
            "seen": counts.get("seen", 0),
            "resolved": counts.get("resolved", 0),
        },
        "items": [_feedback_row_to_dict(row) for row in rows],
    }


async def get_feedback_status(
    pool: asyncpg.Pool, community_key: str, feedback_id: uuid.UUID
) -> str | None:
    return await pool.fetchval(
        "SELECT status FROM feedback_entries WHERE community_key = $1 AND id = $2",
        community_key,
        feedback_id,
    )


async def get_feedback_item(
    pool: asyncpg.Pool, community_key: str, feedback_id: uuid.UUID
) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        """
        SELECT id, rating, comment, page_url, page_title, page_path, locale, timezone,
               viewport_width, viewport_height, screen_width, screen_height, color_scheme,
               client_timestamp, extra_context, screenshot_bytes IS NOT NULL AS has_screenshot,
               status, seen_at, resolved_at, created_at
        FROM feedback_entries
        WHERE community_key = $1 AND id = $2
        """,
        community_key,
        feedback_id,
    )
    return _feedback_row_to_dict(row) if row else None


async def get_feedback_screenshot(
    pool: asyncpg.Pool, community_key: str, feedback_id: uuid.UUID
) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        "SELECT screenshot_bytes, screenshot_mime_type FROM feedback_entries "
        "WHERE community_key = $1 AND id = $2",
        community_key,
        feedback_id,
    )
    return dict(row) if row else None


async def update_feedback_status(
    pool: asyncpg.Pool,
    community_key: str,
    feedback_id: uuid.UUID,
    *,
    status: str,
    actor_id: str,
) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        """
        UPDATE feedback_entries
        SET status = $3,
            seen_at = COALESCE(seen_at, now()),
            resolved_at = CASE WHEN $3 = 'resolved' THEN COALESCE(resolved_at, now())
                               ELSE resolved_at END,
            status_updated_by = $4
        WHERE community_key = $1 AND id = $2
          AND CASE status WHEN 'new' THEN 0 WHEN 'seen' THEN 1 ELSE 2 END
              <= CASE $3 WHEN 'new' THEN 0 WHEN 'seen' THEN 1 ELSE 2 END
        RETURNING id, rating, comment, page_url, page_title, page_path, locale, timezone,
                  viewport_width, viewport_height, screen_width, screen_height, color_scheme,
                  client_timestamp, extra_context, screenshot_bytes IS NOT NULL AS has_screenshot,
                  status, seen_at, resolved_at, created_at
        """,
        community_key,
        feedback_id,
        status,
        actor_id,
    )
    return _feedback_row_to_dict(row) if row else None


def _feedback_row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    result: dict[str, Any] = dict(row)
    extra = result.pop("extra_context", None)
    result["extra"] = json.loads(extra) if isinstance(extra, str) else (extra or {})
    return result


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
