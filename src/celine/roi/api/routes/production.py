"""POST /api/v1/production — fetch PV production data from PVGIS or Trentino Solar."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from celine.roi.api.deps import ConfigDep
from celine.roi.api.schemas import ErrorResponse, ProductionDataResponse, ProductionRequest
from celine.roi.models import SystemInput
from celine.roi.pvgis_client import fetch_production

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/production",
    response_model=ProductionDataResponse,
    responses={
        502: {"model": ErrorResponse, "description": "PVGIS or Trentino Solar API unreachable"},
        504: {"model": ErrorResponse, "description": "External API timeout"},
    },
    summary="Fetch PV production data",
    description=(
        "Fetches monthly production data from PVGIS (JRC API) and optionally "
        "the Trentino Solar LIDAR API for shadow-corrected output. "
        "Returns a 12-element monthly array and the annual total. "
        "When annual_production_kwh is provided no external call is made — "
        "the total is distributed synthetically using a 46°N solar curve."
    ),
)
async def fetch_production_endpoint(
    request: ProductionRequest,
    config: ConfigDep,
) -> ProductionDataResponse:
    # Build a minimal SystemInput — only the fields used by fetch_production
    system_input = SystemInput(
        kwp=request.kwp,
        latitude=request.latitude,
        longitude=request.longitude,
        tilt=request.tilt,
        azimuth=request.azimuth,
        capex=1.0,
        annual_consumption_kwh=1.0,
        user_type="commercial",
        regime="RID",
        equity_fraction=1.0,
        loan_rate=0.0,
        loan_duration_years=0,
        annual_production_kwh=request.annual_production_kwh,
        rooftop_wkt=request.rooftop_wkt,
    )

    try:
        production = await fetch_production(system_input)
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return ProductionDataResponse.from_domain(production)
