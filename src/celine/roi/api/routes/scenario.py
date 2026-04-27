"""POST /api/v1/scenario — run the full CELINE ROI pipeline in one call."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException

from celine.roi.api.database import get_pool, save_estimate
from celine.roi.api.deps import ConfigDep, apply_config_overrides
from celine.roi.api.routes._converters import to_system_input
from celine.roi.api.schemas import ErrorResponse, ScenarioResultResponse, ScenarioRunRequest
from celine.roi.main import run_scenario

logger = logging.getLogger(__name__)
router = APIRouter()


async def _persist_estimate(
    endpoint: str,
    status: str,
    request_body: dict,
    response_body: dict | None,
    duration_ms: int,
    error_message: str | None = None,
) -> None:
    pool = get_pool()
    if pool is None:
        return
    try:
        await save_estimate(
            pool=pool,
            endpoint=endpoint,
            status=status,
            request=request_body,
            response=response_body,
            duration_ms=duration_ms,
            error_message=error_message,
        )
    except Exception:
        logger.exception("Failed to persist estimate")


@router.post(
    "/scenario",
    response_model=ScenarioResultResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid parameters"},
        502: {"model": ErrorResponse, "description": "PVGIS or Trentino Solar API unreachable"},
        504: {"model": ErrorResponse, "description": "External API timeout"},
    },
    summary="Run full ROI scenario",
    description=(
        "Convenience endpoint that runs the complete CELINE ROI pipeline in one call: "
        "production fetch → energy matching → incentives → finance → validation. "
        "Returns all intermediate results plus a top-level KPI summary. "
        "HTTP 200 is returned even when validation.fails is non-empty — "
        "check summary.is_valid or validation.fails to assess scenario viability. "
        "Use config_overrides to vary assumptions (WACC, tariffs, sharing ratio) "
        "for sensitivity analysis without changing server configuration."
    ),
)
async def run_scenario_endpoint(
    request: ScenarioRunRequest,
    config: ConfigDep,
    background_tasks: BackgroundTasks,
) -> ScenarioResultResponse:
    effective_config = apply_config_overrides(config, request.config_overrides)
    system_input = to_system_input(request.system)
    request_body = request.model_dump(mode="json")

    t0 = time.monotonic()
    try:
        result = await run_scenario(system_input, effective_config)
    except (ConnectionError, TimeoutError, ValueError, AssertionError) as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        status_code = {ConnectionError: 502, TimeoutError: 504, ValueError: 400}.get(
            type(exc), 500
        )
        background_tasks.add_task(
            _persist_estimate,
            endpoint="scenario",
            status="error",
            request_body=request_body,
            response_body=None,
            duration_ms=duration_ms,
            error_message=str(exc),
        )
        if isinstance(exc, AssertionError):
            logger.error("Energy balance assertion failed: %s", exc)
        raise HTTPException(status_code=status_code, detail=str(exc))

    duration_ms = int((time.monotonic() - t0) * 1000)
    response_obj = ScenarioResultResponse.from_domain(result)
    background_tasks.add_task(
        _persist_estimate,
        endpoint="scenario",
        status="success",
        request_body=request_body,
        response_body=response_obj.model_dump(mode="json"),
        duration_ms=duration_ms,
    )

    return response_obj
