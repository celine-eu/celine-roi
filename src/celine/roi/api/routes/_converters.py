"""Domain object conversion helpers shared across route handlers.

These functions convert Pydantic request/response schemas into the internal
frozen dataclasses expected by the engine functions.
"""

from __future__ import annotations

import numpy as np

from celine.roi.api.schemas import (
    EnergyResultResponse,
    FinanceResultResponse,
    IncentiveResultResponse,
    SystemInputRequest,
)
from celine.roi.models import EnergyResult, FinanceResult, IncentiveResult, SystemInput


def to_system_input(s: SystemInputRequest) -> SystemInput:
    return SystemInput(
        kwp=s.kwp,
        latitude=s.latitude,
        longitude=s.longitude,
        tilt=s.tilt,
        azimuth=s.azimuth,
        capex=s.capex,
        annual_consumption_kwh=s.annual_consumption_kwh,
        user_type=s.user_type,
        regime=s.regime,
        equity_fraction=s.equity_fraction,
        loan_rate=s.loan_rate,
        loan_duration_years=s.loan_duration_years,
        annual_production_kwh=s.annual_production_kwh,
        location=s.location,
        rooftop_wkt=s.rooftop_wkt,
        abitazione_principale=s.abitazione_principale,
        heat_pump_kwh_annual=s.heat_pump_kwh_annual,
        battery_kwh=s.battery_kwh,
    )


def to_energy_result(e: EnergyResultResponse) -> EnergyResult:
    return EnergyResult(
        production=np.array(e.production),
        consumption=np.array(e.consumption),
        autoconsumo=np.array(e.autoconsumo),
        immissione=np.array(e.immissione),
        prelievo=np.array(e.prelievo),
        energia_condivisa=np.array(e.energia_condivisa),
        tasso_autoconsumo=e.tasso_autoconsumo,
    )


def to_incentive_result(i: IncentiveResultResponse) -> IncentiveResult:
    return IncentiveResult(
        years=np.array(i.years),
        production_degraded=np.array(i.production_degraded),
        risparmio_autoconsumo=np.array(i.risparmio_autoconsumo),
        rid_revenue=np.array(i.rid_revenue),
        cer_tip=np.array(i.cer_tip),
        cer_cacv=np.array(i.cer_cacv),
        cer_tip_libero=np.array(i.cer_tip_libero),
        cer_cacv_libero=np.array(i.cer_cacv_libero),
        cer_tip_vincolato=np.array(i.cer_tip_vincolato),
        cer_cacv_vincolato=np.array(i.cer_cacv_vincolato),
        ammortamento=np.array(i.ammortamento),
        tax_shield=np.array(i.tax_shield),
        ires_irap=np.array(i.ires_irap),
        detrazione_irpef=np.array(i.detrazione_irpef),
    )


def to_finance_result(f: FinanceResultResponse) -> FinanceResult:
    return FinanceResult(
        cashflows=np.array(f.cashflows),
        cumulative=np.array(f.cumulative),
        npv=f.npv,
        irr=f.irr,
        payback_simple=f.payback_simple,
        payback_discounted=f.payback_discounted,
        dscr=np.array(f.dscr) if f.dscr is not None else None,
    )
