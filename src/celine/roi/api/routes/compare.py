"""POST /api/v1/compare — compare multiple scenarios side-by-side."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from celine.roi.api.database import get_pool, save_estimate
from celine.roi.api.deps import ConfigDep, apply_config_overrides
from celine.roi.api.routes._converters import to_system_input
from celine.roi.api.schemas import (
    ConfigOverrides,
    ErrorResponse,
    ScenarioResultResponse,
    SystemInputRequest,
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
    "/compare",
    response_model=CompareResponse,
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Compare multiple scenarios",
    description=(
        "Run N named scenarios with different parameter overrides "
        "and return a side-by-side comparison table."
    ),
)
async def compare_endpoint(
    request: CompareRequest,
    config: ConfigDep,
    background_tasks: BackgroundTasks,
) -> CompareResponse:
    effective_config = apply_config_overrides(config, request.config_overrides)
    system_input = to_system_input(request.system)
    request_body = request.model_dump(mode="json")

    t0 = time.monotonic()
    try:
        result = await compare_scenarios(system_input, effective_config, request.scenarios)
    except ConnectionError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        background_tasks.add_task(
            _persist_estimate,
            endpoint="compare",
            status="error",
            request_body=request_body,
            response_body=None,
            duration_ms=duration_ms,
            error_message=str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        background_tasks.add_task(
            _persist_estimate,
            endpoint="compare",
            status="error",
            request_body=request_body,
            response_body=None,
            duration_ms=duration_ms,
            error_message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc))

    duration_ms = int((time.monotonic() - t0) * 1000)
    response_obj = CompareResponse(
        scenarios={
            name: ScenarioResultResponse.from_domain(sr) for name, sr in result.scenarios.items()
        },
        summary_table=result.summary_table,
    )
    background_tasks.add_task(
        _persist_estimate,
        endpoint="compare",
        status="success",
        request_body=request_body,
        response_body=response_obj.model_dump(mode="json"),
        duration_ms=duration_ms,
    )

    return response_obj
