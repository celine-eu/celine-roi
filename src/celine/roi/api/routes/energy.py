"""POST /api/v1/energy — compute monthly energy matching from production data."""

from __future__ import annotations

import logging

import numpy as np
from fastapi import APIRouter, HTTPException

from celine.roi.api.deps import ConfigDep, apply_config_overrides
from celine.roi.api.routes._converters import to_system_input
from celine.roi.api.schemas import (
    EnergyRequest,
    EnergyResultResponse,
    ErrorResponse,
    ProductionDataResponse,
)
from celine.roi.engines.energy import compute_energy
from celine.roi.models import ProductionData

logger = logging.getLogger(__name__)
router = APIRouter()


def _production_from_response(p: ProductionDataResponse) -> ProductionData:
    return ProductionData(
        monthly_production_kwh=np.array(p.monthly_production_kwh),
        annual_production_kwh=p.annual_production_kwh,
        source=p.source,
        effective_kwp=p.effective_kwp,
    )


@router.post(
    "/energy",
    response_model=EnergyResultResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Energy balance invariant violated"},
    },
    summary="Compute energy matching",
    description=(
        "Computes year-1 monthly energy matching: self-consumption, grid export, "
        "grid draw, and shared energy (CER). Pass the ProductionDataResponse from "
        "POST /production as the production field."
    ),
)
async def compute_energy_endpoint(
    request: EnergyRequest,
    config: ConfigDep,
) -> EnergyResultResponse:
    effective_config = apply_config_overrides(config, request.config_overrides)
    system_input = to_system_input(request.system)
    production_data = _production_from_response(request.production)

    try:
        result = compute_energy(system_input, production_data, effective_config)
    except (ValueError, AssertionError) as exc:
        logger.error("Energy computation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    return EnergyResultResponse.from_domain(result)
