"""POST /api/v1/validate — run all validation checks on a completed scenario."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from celine.roi.api.deps import ConfigDep, apply_config_overrides
from celine.roi.api.routes._converters import (
    to_energy_result,
    to_finance_result,
    to_incentive_result,
    to_system_input,
)
from celine.roi.api.schemas import (
    EnergyResultResponse,
    ErrorResponse,
    FinanceResultResponse,
    IncentiveResultResponse,
    ValidateRequest,
    ValidationReportResponse,
)
from celine.roi.validation.warnings import validate_model

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/validate",
    response_model=ValidationReportResponse,
    summary="Run validation checks",
    description=(
        "Runs all regulatory and model validation checks against a completed scenario. "
        "Returns categorised results: fails (blocking), warns (advisory), passes. "
        "HTTP 200 is always returned — callers check is_valid or the fails list. "
        "Pass the outputs from POST /energy, /incentives, and /finance."
    ),
)
async def validate_endpoint(
    request: ValidateRequest,
    config: ConfigDep,
) -> ValidationReportResponse:
    effective_config = apply_config_overrides(config, request.config_overrides)
    system_input = to_system_input(request.system)
    energy_result = to_energy_result(request.energy)
    incentive_result = to_incentive_result(request.incentives)
    finance_result = to_finance_result(request.finance)

    try:
        report = validate_model(
            system_input, energy_result, incentive_result, finance_result, effective_config
        )
    except Exception as exc:
        logger.error("Validation failed unexpectedly: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return ValidationReportResponse.from_domain(report)
