"""Pydantic v2 request and response schemas for the CELINE ROI API.

Internal domain objects (frozen dataclasses in models.py) are never exposed
directly. Conversion happens at route boundaries via from_domain() classmethods
on response models and explicit mapping helpers in route handlers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ── Shared literals ────────────────────────────────────────────────────────────

UserType = Literal["residential", "office", "commercial", "industrial", "agricultural"]
Regime = Literal["RID", "RID_CER"]


# ── Config overrides ───────────────────────────────────────────────────────────

class ConfigOverrides(BaseModel):
    """Per-request overrides for a subset of server config parameters.

    All fields are optional; None means use the server default.
    Only parameters that make sense to vary per-request are exposed here.
    Tax rates, depreciation schedules, and useful_life are server policy.
    """

    wacc: float | None = Field(
        default=None,
        ge=0.001,
        le=0.30,
        description="Weighted Average Cost of Capital (e.g. 0.055 = 5.5%)",
    )
    retail_price: float | None = Field(
        default=None,
        ge=0.05,
        le=0.80,
        description="Grid electricity retail price EUR/kWh",
    )
    sharing_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="CER energy sharing ratio (0.4–0.7 typical)",
    )
    energy_inflation: float | None = Field(
        default=None,
        ge=0.0,
        le=0.20,
        description="Annual energy price inflation rate",
    )
    rid_tariff: float | None = Field(
        default=None,
        ge=0.01,
        le=0.30,
        description="RID feed-in tariff EUR/kWh",
    )
    cer_tip: float | None = Field(
        default=None,
        ge=0.01,
        le=0.30,
        description="CER TIP incentive tariff EUR/kWh (fixed nominal per decree)",
    )
    cer_cacv: float | None = Field(
        default=None,
        ge=0.001,
        le=0.10,
        description="CER Cacv component EUR/kWh",
    )
    load_profile: str | None = Field(
        default=None,
        description="Load profile filename (e.g., 'residential_heat_pump.json')",
    )
    detrazione_enabled: bool | None = Field(
        default=None,
        description="Enable/disable IRPEF deduction (default: True when eligible). "
                    "Set False to skip even for residential users.",
    )
    detrazione_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Override IRPEF deduction rate (e.g. 0.50 = 50%). "
                    "Overrides both primary/other rates.",
    )
    detrazione_years: int | None = Field(
        default=None,
        ge=1,
        le=30,
        description="Override number of years for IRPEF deduction installments (default: 10)",
    )
    detrazione_include_iva: bool | None = Field(
        default=None,
        description="When true, deductible base = CAPEX × (1 + IVA rate). Default: true.",
    )
    cer_virtual_consumption_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of grid-exported energy virtually consumed within CER (0-1). "
                    "1.0 = all exported matched by CER members (optimistic). "
                    "0.5 = only half matched (realistic for small CERs).",
    )


# ── System input request ───────────────────────────────────────────────────────

class SystemInputRequest(BaseModel):
    """System and investment parameters for a CELINE ROI scenario.

    Maps 1:1 to the SystemInput domain object.
    """

    kwp: float = Field(
        ge=0.0,
        le=5000.0,
        description="Installed PV capacity kWp. May be 0 when rooftop_wkt is provided.",
    )
    latitude: float = Field(ge=35.0, le=48.0, description="Site latitude (Italy: 35–48°N)")
    longitude: float = Field(ge=6.0, le=19.0, description="Site longitude (Italy: 6–19°E)")
    tilt: float = Field(default=30.0, ge=0.0, le=90.0, description="Panel tilt in degrees")
    azimuth: float = Field(
        default=0.0,
        ge=-180.0,
        le=180.0,
        description="Panel azimuth in degrees (0=south, 90=west, -90=east)",
    )
    capex: float = Field(gt=0.0, description="Total CAPEX in EUR (net of IVA)")
    annual_consumption_kwh: float = Field(ge=0.0, description="Annual site consumption kWh (0 = pure export)")
    user_type: UserType = Field(default="commercial")
    regime: Regime = Field(default="RID_CER")
    equity_fraction: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of CAPEX paid with equity (1.0 = fully self-funded)",
    )
    loan_rate: float = Field(default=0.0, ge=0.0, le=0.30, description="Annual loan interest rate")
    loan_duration_years: int = Field(default=0, ge=0, le=30, description="Loan term in years")
    annual_production_kwh: float | None = Field(
        default=None,
        gt=0.0,
        description="Manual annual production override — skips PVGIS fetch when set",
    )
    location: str = Field(default="", max_length=200, description="Human-readable site name")
    abitazione_principale: bool = Field(
        default=True,
        description="Primary residence flag. Affects IRPEF deduction rate: "
                    "50% for primary (2026), 36% for other residential.",
    )
    rooftop_wkt: str | None = Field(
        default=None,
        description="WKT polygon of rooftop for Trentino Solar LIDAR API (Trentino only)",
    )
    heat_pump_kwh_annual: float = Field(
        default=0.0,
        ge=0.0,
        le=50000.0,
        description=(
            "Additional annual electricity consumed by a heat pump in kWh. "
            "When > 0, the HP load (daytime-heavy) is blended on top of the base "
            "user_type profile. Works for all user types. "
            "Typical Italian residential: 2500-4500 kWh/year. 0 = no heat pump."
        ),
    )
    battery_kwh: float = Field(
        default=0.0,
        ge=0.0,
        le=200.0,
        description=(
            "Battery storage capacity in kWh. When > 0, estimated battery cost "
            "(based on battery_cost_per_kwh config) is subtracted from CAPEX to "
            "isolate PV-only investment for financial analysis. "
            "Does NOT affect energy matching (no dispatch model yet). "
            "Typical residential: 5-15 kWh. 0 = no battery."
        ),
    )
    custom_hourly_kwh: list[float] | None = Field(
        default=None,
        min_length=24,
        max_length=24,
        description=(
            "Personal consumption profile: 24 mean kWh values (one per hour, "
            "00:00-23:00). Overrides the default user_type profile. "
            "Example: [0.2, 0.15, 0.1, ..., 0.5] representing average hourly "
            "consumption in kWh."
        ),
    )
    custom_profile_dir: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Personal consumption profile from smart meter data: folder name "
            "inside config/load_profiles/ containing daily JSON files "
            "(YYYY-MM-DD.json format from C2G/e-distribuzione). "
            "Example: 'IT221E00549903'"
        ),
    )

    @model_validator(mode="after")
    def validate_loan_consistency(self) -> "SystemInputRequest":
        if self.equity_fraction < 1.0:
            if self.loan_duration_years == 0:
                raise ValueError("loan_duration_years must be > 0 when equity_fraction < 1.0")
            if self.loan_rate == 0.0:
                raise ValueError("loan_rate must be > 0 when equity_fraction < 1.0")
        return self

    @model_validator(mode="after")
    def validate_capacity_source(self) -> "SystemInputRequest":
        if self.kwp == 0.0 and self.rooftop_wkt is None:
            raise ValueError("Either kwp > 0 or rooftop_wkt must be provided")
        return self


# ── Phase-specific request models ─────────────────────────────────────────────

class ProductionRequest(BaseModel):
    """Request to fetch PV production data only (PVGIS or Trentino Solar)."""

    kwp: float = Field(ge=0.0, le=5000.0)
    latitude: float = Field(ge=35.0, le=48.0)
    longitude: float = Field(ge=6.0, le=19.0)
    tilt: float = Field(default=30.0, ge=0.0, le=90.0)
    azimuth: float = Field(default=0.0, ge=-180.0, le=180.0)
    annual_production_kwh: float | None = Field(
        default=None,
        gt=0.0,
        description="When set, skips external API and distributes this total synthetically",
    )
    rooftop_wkt: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_capacity_source(self) -> "ProductionRequest":
        if self.kwp == 0.0 and self.rooftop_wkt is None and self.annual_production_kwh is None:
            raise ValueError(
                "At least one of kwp > 0, rooftop_wkt, or annual_production_kwh must be provided"
            )
        return self


class EnergyRequest(BaseModel):
    """Request to compute energy matching from production data."""

    system: SystemInputRequest
    production: "ProductionDataResponse"
    config_overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)


class IncentivesRequest(BaseModel):
    """Request to compute 25-year incentive cashflows from energy matching."""

    system: SystemInputRequest
    energy: "EnergyResultResponse"
    config_overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)


class FinanceRequest(BaseModel):
    """Request to compute full financial analysis from incentive cashflows."""

    system: SystemInputRequest
    incentives: "IncentiveResultResponse"
    config_overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)


class ValidateRequest(BaseModel):
    """Request to run all validation checks on a completed scenario."""

    system: SystemInputRequest
    energy: "EnergyResultResponse"
    incentives: "IncentiveResultResponse"
    finance: "FinanceResultResponse"
    config_overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)


class ScenarioRunRequest(BaseModel):
    """Full pipeline request: runs all phases in sequence."""

    system: SystemInputRequest
    config_overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)


# ── Response models ────────────────────────────────────────────────────────────

class ProductionDataResponse(BaseModel):
    """Monthly PV production data."""

    monthly_production_kwh: list[float] = Field(
        description="12-element array of monthly production kWh"
    )
    annual_production_kwh: float
    source: Literal["pvgis", "synthetic", "trentino+pvgis"]
    effective_kwp: float | None = Field(
        default=None,
        description="kWp from Trentino LIDAR polygon; None for other sources",
    )

    @classmethod
    def from_domain(cls, obj: object) -> "ProductionDataResponse":
        return cls(
            monthly_production_kwh=obj.monthly_production_kwh.tolist(),  # type: ignore[attr-defined]
            annual_production_kwh=obj.annual_production_kwh,  # type: ignore[attr-defined]
            source=obj.source,  # type: ignore[attr-defined]
            effective_kwp=obj.effective_kwp,  # type: ignore[attr-defined]
        )


class EnergyResultResponse(BaseModel):
    """Year-1 monthly energy matching results."""

    production: list[float] = Field(description="Monthly production kWh (12 values)")
    consumption: list[float] = Field(description="Monthly consumption kWh (flat distribution)")
    autoconsumo: list[float] = Field(description="Monthly self-consumed kWh")
    immissione: list[float] = Field(description="Monthly grid export kWh")
    prelievo: list[float] = Field(description="Monthly grid draw kWh")
    energia_condivisa: list[float] = Field(description="Monthly shared energy kWh (CER)")
    tasso_autoconsumo: float = Field(description="Annual self-consumption ratio (0–1)")

    @classmethod
    def from_domain(cls, obj: object) -> "EnergyResultResponse":
        return cls(
            production=obj.production.tolist(),  # type: ignore[attr-defined]
            consumption=obj.consumption.tolist(),  # type: ignore[attr-defined]
            autoconsumo=obj.autoconsumo.tolist(),  # type: ignore[attr-defined]
            immissione=obj.immissione.tolist(),  # type: ignore[attr-defined]
            prelievo=obj.prelievo.tolist(),  # type: ignore[attr-defined]
            energia_condivisa=obj.energia_condivisa.tolist(),  # type: ignore[attr-defined]
            tasso_autoconsumo=obj.tasso_autoconsumo,  # type: ignore[attr-defined]
        )


class IncentiveResultResponse(BaseModel):
    """25-year incentive and depreciation cashflow arrays."""

    years: list[int] = Field(description="Year indices [1..25]")
    production_degraded: list[float] = Field(description="Annual production after degradation kWh")
    risparmio_autoconsumo: list[float] = Field(description="Annual self-consumption savings EUR")
    rid_revenue: list[float] = Field(description="Annual RID feed-in revenue EUR")
    cer_tip: list[float] = Field(description="Annual CER TIP incentive EUR (0 after year 20)")
    cer_cacv: list[float] = Field(description="Annual CER Cacv component EUR (0 after year 20)")
    cer_tip_libero: list[float] = Field(
        description="CER TIP libero portion (available to producer) EUR"
    )
    cer_cacv_libero: list[float] = Field(
        description="CER Cacv libero portion (available to producer) EUR"
    )
    cer_tip_vincolato: list[float] = Field(
        description="CER TIP vincolato portion (distributed to CER members) EUR"
    )
    cer_cacv_vincolato: list[float] = Field(
        description="CER Cacv vincolato portion (distributed to CER members) EUR"
    )
    ammortamento: list[float] = Field(description="Annual fiscal depreciation EUR")
    tax_shield: list[float] = Field(description="Annual IRES tax shield from depreciation EUR")
    ires_irap: list[float] = Field(description="Annual IRES+IRAP tax on RID+CER revenue EUR")
    detrazione_irpef: list[float] = Field(
        description="Annual IRPEF tax credit EUR (residential <=20 kWp only, 0 otherwise)"
    )

    @classmethod
    def from_domain(cls, obj: object) -> "IncentiveResultResponse":
        return cls(
            years=obj.years.tolist(),  # type: ignore[attr-defined]
            production_degraded=obj.production_degraded.tolist(),  # type: ignore[attr-defined]
            risparmio_autoconsumo=obj.risparmio_autoconsumo.tolist(),  # type: ignore[attr-defined]
            rid_revenue=obj.rid_revenue.tolist(),  # type: ignore[attr-defined]
            cer_tip=obj.cer_tip.tolist(),  # type: ignore[attr-defined]
            cer_cacv=obj.cer_cacv.tolist(),  # type: ignore[attr-defined]
            cer_tip_libero=obj.cer_tip_libero.tolist(),  # type: ignore[attr-defined]
            cer_cacv_libero=obj.cer_cacv_libero.tolist(),  # type: ignore[attr-defined]
            cer_tip_vincolato=obj.cer_tip_vincolato.tolist(),  # type: ignore[attr-defined]
            cer_cacv_vincolato=obj.cer_cacv_vincolato.tolist(),  # type: ignore[attr-defined]
            ammortamento=obj.ammortamento.tolist(),  # type: ignore[attr-defined]
            tax_shield=obj.tax_shield.tolist(),  # type: ignore[attr-defined]
            ires_irap=obj.ires_irap.tolist(),  # type: ignore[attr-defined]
            detrazione_irpef=obj.detrazione_irpef.tolist(),  # type: ignore[attr-defined]
        )


class FinanceResultResponse(BaseModel):
    """25-year discounted cashflow analysis results."""

    cashflows: list[float] = Field(description="Annual cashflows EUR (index 0 = year-0 equity outlay)")
    cumulative: list[float] = Field(description="Cumulative cashflows EUR")
    npv: float = Field(description="Net Present Value at WACC EUR")
    irr: float = Field(description="Internal Rate of Return (decimal, e.g. 0.12 = 12%)")
    payback_simple: float = Field(description="Simple payback period years (inf if never)")
    payback_discounted: float = Field(description="Discounted payback period years (inf if never)")
    dscr: list[float] | None = Field(
        default=None,
        description="Annual Debt Service Coverage Ratio for loan years; None if no debt",
    )

    @classmethod
    def from_domain(cls, obj: object) -> "FinanceResultResponse":
        return cls(
            cashflows=obj.cashflows.tolist(),  # type: ignore[attr-defined]
            cumulative=obj.cumulative.tolist(),  # type: ignore[attr-defined]
            npv=obj.npv,  # type: ignore[attr-defined]
            irr=obj.irr,  # type: ignore[attr-defined]
            payback_simple=obj.payback_simple,  # type: ignore[attr-defined]
            payback_discounted=obj.payback_discounted,  # type: ignore[attr-defined]
            dscr=obj.dscr.tolist() if obj.dscr is not None else None,  # type: ignore[attr-defined]
        )


class CheckResult(BaseModel):
    """A single validation check outcome."""

    code: str = Field(description="Machine-readable check identifier")
    message: str = Field(description="Human-readable description")


class ValidationReportResponse(BaseModel):
    """Full validation report with categorised check results."""

    fails: list[CheckResult] = Field(description="Regulatory or model failures blocking the scenario")
    warns: list[CheckResult] = Field(description="Parameter warnings (scenario still valid)")
    passes: list[CheckResult] = Field(description="Checks that passed")
    is_valid: bool = Field(description="True when fails is empty")

    @classmethod
    def from_domain(cls, obj: object) -> "ValidationReportResponse":
        return cls(
            fails=[CheckResult(code=c, message=m) for c, m in obj.fails],  # type: ignore[attr-defined]
            warns=[CheckResult(code=c, message=m) for c, m in obj.warns],  # type: ignore[attr-defined]
            passes=[CheckResult(code=c, message=m) for c, m in obj.passes],  # type: ignore[attr-defined]
            is_valid=len(obj.fails) == 0,  # type: ignore[attr-defined]
        )


class ScenarioSummary(BaseModel):
    """High-level financial KPIs extracted from a full scenario result."""

    npv_eur: float
    irr_pct: float = Field(description="IRR as percentage (e.g. 12.3 means 12.3%)")
    payback_simple_years: float
    payback_discounted_years: float
    annual_production_kwh: float
    tasso_autoconsumo_pct: float = Field(
        description="Self-consumption ratio as percentage (e.g. 45.2 means 45.2%)"
    )
    source: str = Field(description="Production data source: pvgis / synthetic / trentino+pvgis")
    is_valid: bool


class ScenarioResultResponse(BaseModel):
    """Complete scenario result containing all pipeline phase outputs."""

    summary: ScenarioSummary
    production: ProductionDataResponse
    energy: EnergyResultResponse
    incentives: IncentiveResultResponse
    finance: FinanceResultResponse
    validation: ValidationReportResponse

    @classmethod
    def from_domain(cls, result: object) -> "ScenarioResultResponse":
        fin = result.finance  # type: ignore[attr-defined]
        prod = result.production  # type: ignore[attr-defined]
        energy = result.energy  # type: ignore[attr-defined]
        val = result.validation  # type: ignore[attr-defined]
        return cls(
            summary=ScenarioSummary(
                npv_eur=fin.npv,
                irr_pct=fin.irr * 100.0,
                payback_simple_years=fin.payback_simple,
                payback_discounted_years=fin.payback_discounted,
                annual_production_kwh=prod.annual_production_kwh,
                tasso_autoconsumo_pct=energy.tasso_autoconsumo * 100.0,
                source=prod.source,
                is_valid=len(val.fails) == 0,
            ),
            production=ProductionDataResponse.from_domain(prod),
            energy=EnergyResultResponse.from_domain(energy),
            incentives=IncentiveResultResponse.from_domain(result.incentives),  # type: ignore[attr-defined]
            finance=FinanceResultResponse.from_domain(fin),
            validation=ValidationReportResponse.from_domain(val),
        )


# ── Error envelope ─────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error envelope for 4xx/5xx responses."""

    error: str
    detail: str | None = None
