"""POST /api/v1/finance — compute full DCF financial analysis."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from celine.roi.api.deps import ConfigDep, apply_config_overrides
from celine.roi.api.routes._converters import to_incentive_result, to_system_input
from celine.roi.api.schemas import (
    ErrorResponse,
    FinanceRequest,
    FinanceResultResponse,
    IncentiveResultResponse,
)
from celine.roi.engines.finance import compute_finance

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/finance",
    response_model=FinanceResultResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid financial parameters"},
    },
    summary="Compute 25-year financial analysis",
    description=(
        "Computes the full discounted cashflow model: NPV at WACC, IRR, simple and "
        "discounted payback periods, and per-year DSCR when debt is present. "
        "Accounts for O&M costs, insurance, energy price inflation, and inverter "
        "replacement. Pass the IncentiveResultResponse from POST /incentives."
    ),
)
async def compute_finance_endpoint(
    request: FinanceRequest,
    config: ConfigDep,
) -> FinanceResultResponse:
    effective_config = apply_config_overrides(config, request.config_overrides)
    system_input = to_system_input(request.system)
    incentive_result = to_incentive_result(request.incentives)

    try:
        result = compute_finance(system_input, incentive_result, effective_config)
    except (ValueError, AssertionError) as exc:
        logger.error("Finance computation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    return FinanceResultResponse.from_domain(result)
