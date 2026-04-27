"""GET /api/v1/estimates — retrieval endpoints for saved estimates."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

from celine.roi.api.database import get_estimate, get_pool, list_estimates

router = APIRouter()


def _require_pool():
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Estimate persistence is not configured")
    return pool


@router.get(
    "/estimates",
    summary="List saved estimates",
    description="Paginated list of saved estimates, most recent first.",
)
async def list_estimates_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    endpoint: str | None = Query(default=None, pattern="^(scenario|compare)$"),
) -> dict:
    pool = _require_pool()
    return await list_estimates(pool, limit=limit, offset=offset, endpoint=endpoint)


@router.get(
    "/estimates/{estimate_id}",
    summary="Get estimate by ID",
    description="Returns the full estimate record including complete request and response.",
)
async def get_estimate_endpoint(estimate_id: uuid.UUID) -> dict:
    pool = _require_pool()
    record = await get_estimate(pool, estimate_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return record
