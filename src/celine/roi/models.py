"""Data models for the CELINE ROI pipeline.

All models are frozen dataclasses — immutable after creation.
Each represents one stage of the pipeline:
SystemInput → ProductionData → EnergyResult → IncentiveResult → FinanceResult
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class SystemInput:
    """User-provided system parameters and investment details.

    Args:
        kwp: Installed PV capacity in kWp.
        latitude: Site latitude for PVGIS lookup.
        longitude: Site longitude for PVGIS lookup.
        tilt: Panel tilt angle in degrees.
        azimuth: Panel azimuth (0=south, 90=west, -90=east).
        capex: Total investment cost in EUR (net of IVA).
        annual_consumption_kwh: Annual electricity consumption in kWh.
        user_type: Consumer category (residential/office/commercial/industrial/agricultural).
        regime: Incentive regime (RID/CER/RID_CER).
        equity_fraction: Share of CAPEX paid with equity (1.0 = no loan).
        loan_rate: Annual interest rate on debt (0.0 if no loan).
        loan_duration_years: Loan duration in years (0 if no loan).
        annual_production_kwh: Manual override for annual production. Skips PVGIS.
        location: Human-readable site label.
        abitazione_principale: Primary residence flag. Affects IRPEF deduction rate
            (50% for primary in 2026, 36% for other residential).
        heat_pump_kwh_annual: Additional annual electricity consumed by a heat pump in kWh.
            When > 0, the energy engine blends the base user_type load profile with
            the heat_pump_component profile. Works for all user types. 0 = no heat pump.
        battery_kwh: Battery storage capacity in kWh. When > 0, the estimated battery
            cost is subtracted from capex to isolate PV-only investment for financial
            analysis. Does NOT affect energy matching (no dispatch model yet).
    """

    kwp: float
    latitude: float
    longitude: float
    tilt: float
    azimuth: float
    capex: float
    annual_consumption_kwh: float
    user_type: str
    regime: str
    equity_fraction: float
    loan_rate: float
    loan_duration_years: int
    annual_production_kwh: float | None = None
    location: str = ""
    rooftop_wkt: str | None = None  # WKT polygon of rooftop (for Trentino Solar API)
    abitazione_principale: bool = True  # Primary residence — affects IRPEF deduction rate
    heat_pump_kwh_annual: float = 0.0  # Additional HP load — 0 = no heat pump
    battery_kwh: float = 0.0  # Battery capacity — used for cost deduction only


@dataclass(frozen=True)
class ProductionData:
    """Monthly PV production data from PVGIS or synthetic distribution.

    Args:
        monthly_production_kwh: 12-element array of kWh per month (year 1, before degradation).
        annual_production_kwh: Sum of monthly production.
        source: Data origin — "pvgis", "manual", "synthetic", or "trentino+pvgis".
        effective_kwp: Actual installed capacity in kWp. When Trentino API is used,
            this comes from the rooftop polygon (area * 160 W/m²) and may differ
            from the user-provided kwp. None means use system_input.kwp.
        hourly_production_kwh: Optional 8760-element array of hourly production in kWh.
            When available, the energy engine uses this for hourly matching.
    """

    monthly_production_kwh: np.ndarray
    annual_production_kwh: float
    source: str
    effective_kwp: float | None = None
    hourly_production_kwh: np.ndarray | None = None


@dataclass(frozen=True)
class EnergyResult:
    """Energy matching results for one year (before degradation).

    All arrays have the same length (12 for monthly, 8760 for hourly).

    Args:
        production: PV production per period in kWh.
        consumption: Electricity consumption per period in kWh.
        autoconsumo: Self-consumed energy per period in kWh.
        immissione: Energy fed to grid per period in kWh.
        prelievo: Energy drawn from grid per period in kWh.
        energia_condivisa: CER shared energy per period in kWh.
        tasso_autoconsumo: Self-consumption ratio (0.0 to 1.0).
    """

    production: np.ndarray
    consumption: np.ndarray
    autoconsumo: np.ndarray
    immissione: np.ndarray
    prelievo: np.ndarray
    energia_condivisa: np.ndarray
    tasso_autoconsumo: float


@dataclass(frozen=True)
class IncentiveResult:
    """Yearly incentive and tax calculations over the system lifetime.

    All arrays are indexed by year (0 = year 1, length = useful_life).

    Args:
        years: Year numbers (1 to useful_life).
        production_degraded: Annual production after degradation in kWh.
        risparmio_autoconsumo: Annual savings from self-consumption in EUR.
        rid_revenue: Annual RID revenue in EUR.
        cer_tip: Annual CER TIP total incentive in EUR (FIXED nominal, 0 after year 20).
        cer_cacv: Annual CER Cacv total component in EUR (0 after year 20).
        cer_tip_libero: CER TIP libero portion (available to producer) in EUR.
        cer_cacv_libero: CER Cacv libero portion (available to producer) in EUR.
        cer_tip_vincolato: CER TIP vincolato portion (distributed to CER members) in EUR.
        cer_cacv_vincolato: CER Cacv vincolato portion (distributed to CER members) in EUR.
        ammortamento: Annual depreciation amount in EUR.
        tax_shield: Annual tax savings from depreciation in EUR.
        ires_irap: Annual tax on RID + CER revenues in EUR.
        detrazione_irpef: Annual IRPEF tax credit in EUR (residential <=20 kWp only, 0 otherwise).
    """

    years: np.ndarray
    production_degraded: np.ndarray
    risparmio_autoconsumo: np.ndarray
    rid_revenue: np.ndarray
    cer_tip: np.ndarray
    cer_cacv: np.ndarray
    cer_tip_libero: np.ndarray
    cer_cacv_libero: np.ndarray
    cer_tip_vincolato: np.ndarray
    cer_cacv_vincolato: np.ndarray
    ammortamento: np.ndarray
    tax_shield: np.ndarray
    ires_irap: np.ndarray
    detrazione_irpef: np.ndarray


@dataclass(frozen=True)
class FinanceResult:
    """Financial analysis results over the system lifetime.

    Args:
        cashflows: Annual cash flows in EUR (index 0 = year 0 = investment).
        cumulative: Cumulative cash flows in EUR.
        npv: Net Present Value at WACC discount rate in EUR.
        irr: Internal Rate of Return as a decimal.
        payback_simple: Simple payback period in years.
        payback_discounted: Discounted payback period in years.
        dscr: Debt Service Coverage Ratio per year (None if 100% equity).
    """

    cashflows: np.ndarray
    cumulative: np.ndarray
    npv: float
    irr: float
    payback_simple: float
    payback_discounted: float
    dscr: np.ndarray | None = None


@dataclass(frozen=True)
class ValidationReport:
    """Result of model validation checks.

    Args:
        fails: Regulatory blockers — model is invalid.
        warns: Parameter warnings — results may be unreliable.
        passes: Checks that passed successfully.
    """

    fails: list[tuple[str, str]] = field(default_factory=list)
    warns: list[tuple[str, str]] = field(default_factory=list)
    passes: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ScenarioResult:
    """Complete output from a single scenario run.

    Bundles all intermediate results for reporting.
    """

    system_input: SystemInput
    production: ProductionData
    energy: EnergyResult
    incentives: IncentiveResult
    finance: FinanceResult
    validation: ValidationReport


@dataclass(frozen=True)
class ComparisonResult:
    """Side-by-side comparison of multiple scenarios.

    Args:
        scenarios: Ordered dict of scenario name -> full result.
            First entry is always the base case.
        summary_table: Formatted markdown comparison table.
    """

    scenarios: dict[str, ScenarioResult]
    summary_table: str
