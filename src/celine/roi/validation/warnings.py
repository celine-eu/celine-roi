"""Model validation with regulatory checks, parameter warnings, and invariants.

Checks are derived from the 17-error catalog in project_summary.md.
Each check returns FAIL (model invalid), WARN (unreliable), or PASS.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import numpy_financial as npf

from celine.roi.models import (
    EnergyResult,
    FinanceResult,
    IncentiveResult,
    SystemInput,
    ValidationReport,
)

logger = logging.getLogger(__name__)


def validate_model(
    system_input: SystemInput,
    energy: EnergyResult,
    incentives: IncentiveResult,
    finance: FinanceResult,
    config: dict[str, Any],
) -> ValidationReport:
    """Run all validation checks on model inputs and outputs.

    Args:
        system_input: System parameters.
        energy: Energy matching results.
        incentives: Incentive calculations.
        finance: Financial analysis results.
        config: Merged configuration dict.

    Returns:
        ValidationReport with categorized check results.
    """
    fails: list[tuple[str, str]] = []
    warns: list[tuple[str, str]] = []
    passes: list[tuple[str, str]] = []

    # --- Regulatory FAILs ---

    if system_input.regime.upper() in ("SSP", "SCAMBIO_SUL_POSTO"):
        fails.append(("ssp_abolished", "SSP abolished May 2025. Use RID or CER."))
    else:
        passes.append(("ssp_check", "No SSP reference"))

    if system_input.capex <= 0:
        fails.append(("capex_invalid", f"CAPEX must be > 0, got {system_input.capex}"))
    else:
        passes.append(("capex_valid", f"CAPEX = {system_input.capex}"))

    wacc = config.get("wacc", 0.0)
    if wacc <= 0:
        fails.append(("zero_discount_rate", "Discount rate (WACC) must be > 0"))
    else:
        passes.append(("discount_rate_valid", f"WACC = {wacc}"))

    sharing = config.get("sharing_ratio", 0.55)
    if sharing < 0 or sharing > 1.0:
        fails.append(("sharing_ratio_invalid", f"Sharing ratio {sharing} outside [0, 1]"))
    else:
        passes.append(("sharing_ratio_bounds", f"Sharing ratio = {sharing}"))

    if system_input.loan_duration_years > config.get("useful_life", 25):
        fails.append(("loan_exceeds_life",
            f"Loan {system_input.loan_duration_years}y > useful life {config['useful_life']}y"))

    # CER tariff inflation check: CER TIP is fixed nominal, so cer_tip should be
    # monotonically non-increasing over years 1-20 (only degradation applies).
    # If it ever increases year-over-year, inflation was incorrectly applied.
    cer_duration = config.get("cer_duration_years", 20)
    cer_active = incentives.cer_tip[:cer_duration]
    if len(cer_active) >= 2:
        diffs = np.diff(cer_active)
        if np.any(diffs > 0.01):
            fails.append((
                "cer_tip_inflated",
                "CER TIP tariff increases year-over-year — inflation incorrectly applied"
            ))
        else:
            passes.append((
                "cer_tip_fixed",
                "CER TIP tariff is fixed nominal (non-increasing over CER period)"
            ))

    # Self-consumption not taxed check
    if len(incentives.ires_irap) > 0:
        tax_rate = config.get("ires", 0.24) + config.get("irap", 0.039)
        taxable_y1 = incentives.rid_revenue[0] + incentives.cer_tip[0] + incentives.cer_cacv[0]
        expected_tax_y1 = taxable_y1 * tax_rate
        if abs(incentives.ires_irap[0] - expected_tax_y1) < 1.0:
            passes.append(("autoconsumo_not_taxed", "Self-consumption correctly excluded from tax"))
        else:
            fails.append(("autoconsumo_taxed", "Tax calculation includes self-consumption savings"))

    # --- Parameter WARNs ---

    deg = config.get("degradation", 0.0045)
    if deg < 0.003:
        warns.append(("low_degradation", f"Degradation {deg*100:.2f}% below benchmark 0.3-0.6%"))
    elif deg > 0.01:
        warns.append(("high_degradation", f"Degradation {deg*100:.2f}% exceptionally high (>1%)"))
    else:
        passes.append(("degradation_ok", f"Degradation {deg*100:.2f}%"))

    om_per_kwp = config.get("om_per_kwp", 12)
    if om_per_kwp < 5:
        warns.append(("low_om", f"O&M {om_per_kwp} EUR/kWp below benchmark 8-15"))
    else:
        passes.append(("om_ok", f"O&M {om_per_kwp} EUR/kWp"))

    insurance = config.get("insurance_rate", 0.0035)
    if insurance < 0.002:
        warns.append(("low_insurance", f"Insurance {insurance*100:.2f}% below benchmark 0.2-0.5%"))
    else:
        passes.append(("insurance_ok", f"Insurance {insurance*100:.2f}%"))

    if energy.tasso_autoconsumo > 0.80:
        warns.append(("high_autoconsumo",
            f"Self-consumption {energy.tasso_autoconsumo*100:.1f}% — rare without battery"))

    if 0 <= sharing < 0.4 or sharing > 0.7:
        warns.append(("sharing_ratio_atypical", f"Sharing ratio {sharing} outside typical 0.4-0.7"))

    capex_per_kwp = system_input.capex / system_input.kwp if system_input.kwp > 0 else 0
    if capex_per_kwp < 800 or capex_per_kwp > 1500:
        warns.append((
            "capex_per_kwp_atypical",
            f"CAPEX/kWp = {capex_per_kwp:.0f} outside 800-1500"
        ))

    inv_year = config.get("inverter_replacement_year", 0)
    if inv_year == 0:
        warns.append(("no_inverter_replacement", "No inverter replacement modeled"))
    else:
        passes.append(("inverter_replacement_ok", f"Inverter replacement year {inv_year}"))

    if energy.immissione.sum() < 0.01:
        warns.append(("zero_export", "No energy exported — RID and CER incentives will be zero"))

    hp_kwh = system_input.heat_pump_kwh_annual
    if hp_kwh > system_input.annual_consumption_kwh:
        warns.append((
            "heat_pump_oversized",
            f"Heat pump {hp_kwh:.0f} kWh > base consumption {system_input.annual_consumption_kwh:.0f} kWh — "
            "verify HP sizing (typical Italian residential: 2500-4500 kWh/year)"
        ))

    # --- Invariant Checks ---

    balance = abs(energy.autoconsumo.sum() + energy.immissione.sum() - energy.production.sum())
    if balance < 0.01:
        passes.append(("energy_balance", "autoconsumo + immissione == production"))
    else:
        fails.append(("energy_balance_violated", f"Balance error: {balance:.4f} kWh"))

    if energy.energia_condivisa.sum() <= energy.immissione.sum() + 0.01:
        passes.append(("cer_within_immissione", "CER shared energy <= immissione"))
    else:
        fails.append(("cer_exceeds_immissione", "CER shared energy > immissione"))

    dep_total = incentives.ammortamento.sum()
    if dep_total <= system_input.capex + 1.0:
        passes.append((
            "depreciation_cap",
            f"Total depreciation {dep_total:.0f} <= CAPEX {system_input.capex:.0f}"
        ))
    else:
        fails.append((
            "depreciation_exceeds_capex",
            f"Depreciation {dep_total:.0f} > CAPEX {system_input.capex:.0f}"
        ))

    if incentives.production_degraded[-1] < incentives.production_degraded[0]:
        passes.append(("production_degrades", "Year 25 production < year 1"))
    else:
        fails.append(("no_degradation", "Production does not decrease over time"))

    if wacc > 0:
        npv_zero = float(npf.npv(0.0, finance.cashflows))
        cf_sum = float(finance.cashflows.sum())
        tolerance = 0.01 * abs(system_input.capex) if system_input.capex > 0 else 1.0
        if abs(npv_zero - cf_sum) < tolerance:
            passes.append(("npv_zero_check", "NPV(r=0) matches sum of cashflows"))
        else:
            fails.append(("npv_zero_mismatch", f"NPV(0)={npv_zero:.2f} vs sum={cf_sum:.2f}"))

    total = len(fails) + len(warns) + len(passes)
    logger.info("Validation: %d FAIL, %d WARN, %d PASS out of %d checks",
        len(fails), len(warns), len(passes), total)

    return ValidationReport(fails=fails, warns=warns, passes=passes)
