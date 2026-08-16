"""POST /api/v1/incentives — compute 25-year incentive cashflows."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from celine.roi.api.deps import ConfigDep, apply_config_overrides
from celine.roi.api.routes._converters import to_energy_result, to_system_input
from celine.roi.api.schemas import (
    ErrorResponse,
    IncentiveResultResponse,
    IncentivesRequest,
)
from celine.roi.engines.incentives import compute_incentives

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/incentives",
    response_model=IncentiveResultResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid computation parameters"},
    },
    summary="Compute 25-year incentive cashflows",
    description=(
        "Computes annual incentive cashflows over 25 years: RID revenue, CER TIP/Cacv, "
        "self-consumption savings, fiscal depreciation, and tax effects. "
        "Accounts for panel degradation, LID, and Italian incentive duration limits. "
        "Pass the EnergyResultResponse from POST /energy as the energy field."
    ),
)
async def compute_incentives_endpoint(
    request: IncentivesRequest,
    config: ConfigDep,
) -> IncentiveResultResponse:
    effective_config = apply_config_overrides(config, request.config_overrides)
    system_input = to_system_input(request.system)
    energy_result = to_energy_result(request.energy)

    try:
        result = compute_incentives(system_input, energy_result, effective_config)
    except (ValueError, AssertionError) as exc:
        logger.error("Incentives computation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    return IncentiveResultResponse.from_domain(result)
