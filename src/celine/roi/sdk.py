"""Public Python API for the CELINE ROI financial engine.

Usage::

    from celine.roi import calculate_roi

    result = calculate_roi(
        kwp=6.0,
        latitude=45.93,
        longitude=11.27,
        capex=7500,
        annual_consumption_kwh=3000,
        user_type="residential",
        regime="RID_CER",
        annual_production_kwh=7200,
    )

    print(f"NPV: {result.finance.npv:.0f} EUR")
    print(f"IRR: {result.finance.irr:.1%}")
    print(f"Payback: {result.finance.payback_simple:.1f} years")
"""

from __future__ import annotations

import asyncio
from typing import Any

from celine.roi.config_loader import load_default_config
from celine.roi.main import run_scenario
from celine.roi.models import ScenarioResult, SystemInput


async def calculate_roi_async(
    kwp: float,
    latitude: float,
    longitude: float,
    capex: float,
    annual_consumption_kwh: float,
    *,
    tilt: float = 30.0,
    azimuth: float = 0.0,
    user_type: str = "commercial",
    regime: str = "RID_CER",
    equity_fraction: float = 1.0,
    loan_rate: float = 0.0,
    loan_duration_years: int = 0,
    annual_production_kwh: float | None = None,
    location: str = "",
    abitazione_principale: bool = True,
    heat_pump_kwh_annual: float = 0.0,
    battery_kwh: float = 0.0,
    config_overrides: dict[str, Any] | None = None,
) -> ScenarioResult:
    """Run a complete PV ROI analysis (async version).

    Args:
        kwp: Installed PV capacity in kWp.
        latitude: Site latitude (Italy: 35-48).
        longitude: Site longitude (Italy: 6-19).
        capex: Total investment cost in EUR (net of IVA).
        annual_consumption_kwh: Annual electricity consumption in kWh.
        tilt: Panel tilt angle in degrees.
        azimuth: Panel azimuth (0=south, 90=west, -90=east).
        user_type: Consumer type (residential/office/commercial/industrial/agricultural).
        regime: Incentive regime (RID/CER/RID_CER).
        equity_fraction: Share of CAPEX paid with equity (1.0 = no loan).
        loan_rate: Annual interest rate on debt.
        loan_duration_years: Loan duration in years.
        annual_production_kwh: Manual production override in kWh (skips PVGIS).
        location: Human-readable site label.
        abitazione_principale: Primary residence flag (affects IRPEF deduction rate).
        heat_pump_kwh_annual: Additional annual heat pump consumption in kWh.
        battery_kwh: Battery capacity in kWh (cost deducted from CAPEX).
        config_overrides: Dict of config parameters to override (e.g. wacc, rid_tariff).

    Returns:
        ScenarioResult with production, energy, incentives, finance, and validation data.
    """
    system_input = SystemInput(
        kwp=kwp,
        latitude=latitude,
        longitude=longitude,
        tilt=tilt,
        azimuth=azimuth,
        capex=capex,
        annual_consumption_kwh=annual_consumption_kwh,
        user_type=user_type,
        regime=regime,
        equity_fraction=equity_fraction,
        loan_rate=loan_rate,
        loan_duration_years=loan_duration_years,
        annual_production_kwh=annual_production_kwh,
        location=location,
        abitazione_principale=abitazione_principale,
        heat_pump_kwh_annual=heat_pump_kwh_annual,
        battery_kwh=battery_kwh,
    )

    config = load_default_config()
    if config_overrides:
        config.update(config_overrides)

    return await run_scenario(system_input, config)


def calculate_roi(
    kwp: float,
    latitude: float,
    longitude: float,
    capex: float,
    annual_consumption_kwh: float,
    *,
    tilt: float = 30.0,
    azimuth: float = 0.0,
    user_type: str = "commercial",
    regime: str = "RID_CER",
    equity_fraction: float = 1.0,
    loan_rate: float = 0.0,
    loan_duration_years: int = 0,
    annual_production_kwh: float | None = None,
    location: str = "",
    abitazione_principale: bool = True,
    heat_pump_kwh_annual: float = 0.0,
    battery_kwh: float = 0.0,
    config_overrides: dict[str, Any] | None = None,
) -> ScenarioResult:
    """Run a complete PV ROI analysis (sync version).

    Convenience wrapper around calculate_roi_async() using asyncio.run().
    If calling from within an existing event loop (e.g. Jupyter, async framework),
    use calculate_roi_async() instead.

    See calculate_roi_async() for full argument documentation.

    Returns:
        ScenarioResult with production, energy, incentives, finance, and validation data.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        raise RuntimeError(
            "calculate_roi() cannot be called from within a running event loop. "
            "Use 'await calculate_roi_async(...)' instead."
        )

    return asyncio.run(
        calculate_roi_async(
            kwp=kwp,
            latitude=latitude,
            longitude=longitude,
            capex=capex,
            annual_consumption_kwh=annual_consumption_kwh,
            tilt=tilt,
            azimuth=azimuth,
            user_type=user_type,
            regime=regime,
            equity_fraction=equity_fraction,
            loan_rate=loan_rate,
            loan_duration_years=loan_duration_years,
            annual_production_kwh=annual_production_kwh,
            location=location,
            abitazione_principale=abitazione_principale,
            heat_pump_kwh_annual=heat_pump_kwh_annual,
            battery_kwh=battery_kwh,
            config_overrides=config_overrides,
        )
    )
