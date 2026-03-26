"""POST /api/v1/scenario — run the full CELINE ROI pipeline in one call."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from celine.roi.api.deps import ConfigDep, apply_config_overrides
from celine.roi.api.routes._converters import to_system_input
from celine.roi.api.schemas import ErrorResponse, ScenarioResultResponse, ScenarioRunRequest
from celine.roi.main import run_scenario

logger = logging.getLogger(__name__)
router = APIRouter()


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
) -> ScenarioResultResponse:
    effective_config = apply_config_overrides(config, request.config_overrides)
    system_input = to_system_input(request.system)

    try:
        result = await run_scenario(system_input, effective_config)
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AssertionError as exc:
        logger.error("Energy balance assertion failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Internal computation error: {exc}")

    return ScenarioResultResponse.from_domain(result)
