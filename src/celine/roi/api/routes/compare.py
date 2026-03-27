"""POST /api/v1/compare — compare multiple scenarios side-by-side."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from celine.roi.api.deps import ConfigDep, apply_config_overrides
from celine.roi.api.routes._converters import to_system_input
from celine.roi.api.schemas import (
    ErrorResponse,
    ScenarioResultResponse,
    SystemInputRequest,
    ConfigOverrides,
)
from celine.roi.scenarios.comparator import compare_scenarios

logger = logging.getLogger(__name__)
router = APIRouter()


class CompareRequest(BaseModel):
    system: SystemInputRequest
    scenarios: dict[str, dict] = Field(
        description="Named scenarios with override dicts. First is base case."
    )
    config_overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)


class CompareResponse(BaseModel):
    scenarios: dict[str, ScenarioResultResponse]
    summary_table: str = Field(description="Markdown comparison table")


@router.post(
    "/compare",
    response_model=CompareResponse,
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Compare multiple scenarios",
    description="Run N named scenarios with different parameter overrides and return a side-by-side comparison table.",
)
async def compare_endpoint(
    request: CompareRequest,
    config: ConfigDep,
) -> CompareResponse:
    effective_config = apply_config_overrides(config, request.config_overrides)
    system_input = to_system_input(request.system)

    try:
        result = await compare_scenarios(system_input, effective_config, request.scenarios)
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return CompareResponse(
        scenarios={
            name: ScenarioResultResponse.from_domain(sr)
            for name, sr in result.scenarios.items()
        },
        summary_table=result.summary_table,
    )
