"""POST /api/v1/capex-estimate — estimate system cost from panel count and rooftop area."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from celine.roi.capex_estimator import estimate_capex, load_panel_specs, max_panels_for_area

logger = logging.getLogger(__name__)
router = APIRouter()

_SPECS_PATH = Path(os.environ.get("CELINE_CONFIG_DIR", "config")) / "panel_specs.yaml"


class CapexEstimateRequest(BaseModel):
    rooftop_area_m2: float = Field(gt=0, description="Available rooftop area in m²")
    num_panels: int | None = Field(
        default=None,
        ge=1,
        description="Number of panels (if None, returns range info only)",
    )


class PanelSpecs(BaseModel):
    watt_peak: int
    area_m2: float
    efficiency_pct: float


class CapexEstimateResponse(BaseModel):
    panel: PanelSpecs
    min_panels: int
    max_panels: int
    num_panels: int | None = None
    kwp: float | None = None
    capex_eur: float | None = None
    eur_per_kwp: float | None = None
    rooftop_utilization_pct: float | None = None


@router.post(
    "/capex-estimate",
    response_model=CapexEstimateResponse,
    summary="Estimate CAPEX from panel count and rooftop area",
    description=(
        "Given a rooftop area, returns panel specs and min/max panel count. "
        "If num_panels is provided, computes CAPEX using a power law cost curve "
        "calibrated on Italian market 2025-2026."
    ),
)
async def capex_estimate_endpoint(request: CapexEstimateRequest) -> CapexEstimateResponse:
    try:
        specs = load_panel_specs(_SPECS_PATH)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Panel specs config not found")

    panel = specs["panel"]
    max_p = max_panels_for_area(request.rooftop_area_m2, specs)
    min_p = specs["bounds"]["min_panels"]

    base_response = CapexEstimateResponse(
        panel=PanelSpecs(
            watt_peak=panel["watt_peak"],
            area_m2=panel["area_m2"],
            efficiency_pct=panel["efficiency_pct"],
        ),
        min_panels=min_p,
        max_panels=max_p,
    )

    if request.num_panels is None:
        return base_response

    try:
        result = estimate_capex(request.num_panels, request.rooftop_area_m2, specs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return CapexEstimateResponse(
        panel=base_response.panel,
        min_panels=min_p,
        max_panels=max_p,
        num_panels=result["num_panels"],
        kwp=result["kwp"],
        capex_eur=result["capex_eur"],
        eur_per_kwp=result["eur_per_kwp"],
        rooftop_utilization_pct=result["rooftop_utilization_pct"],
    )
