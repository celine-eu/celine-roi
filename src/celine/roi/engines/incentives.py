"""Incentive engine for Italian PV systems.

Computes yearly revenue streams, depreciation, and taxation over the system
lifetime, applying production degradation and price escalation.

CRITICAL RULES (non-negotiable):
- CER TIP tariff is FIXED nominal for 20 years — NEVER apply inflation
- CER incentive applies ONLY to shared energy (energia_condivisa)
- Self-consumption (autoconsumo) is NOT taxable — it is an avoided cost
- All rates come from config, NEVER hardcoded
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from celine.roi.models import EnergyResult, IncentiveResult, SystemInput

logger = logging.getLogger(__name__)


def compute_incentives(
    system_input: SystemInput,
    energy_result: EnergyResult,
    config: dict[str, Any],
) -> IncentiveResult:
    """Compute yearly incentives, depreciation, and taxes over system lifetime.

    Args:
        system_input: System parameters (capex, regime).
        energy_result: Year-1 energy matching results (before degradation).
        config: Merged configuration dict.

    Returns:
        IncentiveResult with per-year arrays for all revenue and cost streams.
    """
    useful_life: int = config["useful_life"]
    lid: float = config["lid"]
    degradation: float = config["degradation"]
    cer_duration: int = config["cer_duration_years"]

    retail_price: float = config["retail_price"]
    energy_inflation: float = config["energy_inflation"]
    rid_tariff: float = config["rid_tariff"]
    cer_tip_tariff: float = config["cer_tip"]
    cer_cacv_tariff: float = config["cer_cacv"]

    capex: float = system_input.capex
    dep_coeff: float = config["depreciation_coeff"]
    dep_first_factor: float = config["depreciation_first_year_factor"]

    ires: float = config["ires"]
    irap: float = config["irap"]
    tax_rate: float = ires + irap

    # Year-1 monthly arrays (before degradation) — used for per-year re-matching
    monthly_production = energy_result.production.copy()
    monthly_consumption = energy_result.consumption.copy()
    sharing = config["sharing_ratio"]

    # Allocate output arrays
    years = np.arange(1, useful_life + 1)
    production_degraded = np.zeros(useful_life)
    risparmio_autoconsumo = np.zeros(useful_life)
    rid_revenue = np.zeros(useful_life)
    cer_tip = np.zeros(useful_life)
    cer_cacv = np.zeros(useful_life)
    ammortamento = np.zeros(useful_life)
    tax_shield = np.zeros(useful_life)
    ires_irap = np.zeros(useful_life)

    # Compute depreciation schedule
    cumulative_dep = 0.0
    for idx in range(useful_life):
        year = idx + 1
        if year == 1:
            amount = min(capex * dep_coeff * dep_first_factor, capex - cumulative_dep)
        else:
            amount = min(capex * dep_coeff, capex - cumulative_dep)
        amount = max(0.0, amount)
        ammortamento[idx] = amount
        cumulative_dep += amount

    # Compute yearly values
    for idx in range(useful_life):
        year = idx + 1

        # Degradation factor
        if year == 1:
            deg_factor = 1.0 - lid
        else:
            deg_factor = (1.0 - lid) * (1.0 - degradation) ** (year - 1)

        # Re-run monthly matching on degraded production (more accurate than
        # proportional scaling — avoids ~1% error from nonlinear min/max interaction)
        monthly_prod_degraded = monthly_production * deg_factor
        monthly_auto = np.minimum(monthly_prod_degraded, monthly_consumption)
        monthly_imm = monthly_prod_degraded - monthly_auto

        prod_year = float(monthly_prod_degraded.sum())
        autoconsumo_year = float(monthly_auto.sum())
        immissione_year = float(monthly_imm.sum())
        condivisa_year = immissione_year * sharing

        production_degraded[idx] = prod_year

        # Escalated prices
        retail_year = retail_price * (1.0 + energy_inflation) ** (year - 1)
        rid_tariff_year = rid_tariff * (1.0 + energy_inflation) ** (year - 1)
        cacv_tariff_year = cer_cacv_tariff * (1.0 + energy_inflation) ** (year - 1)

        # Revenue streams
        risparmio_autoconsumo[idx] = autoconsumo_year * retail_year
        rid_revenue[idx] = immissione_year * rid_tariff_year

        # CER incentives — only for first cer_duration years
        if year <= cer_duration:
            cer_tip[idx] = condivisa_year * cer_tip_tariff  # FIXED nominal
            cer_cacv[idx] = condivisa_year * cacv_tariff_year

        # Tax shield from depreciation
        tax_shield[idx] = ammortamento[idx] * ires

        # Taxation on RID + CER only (autoconsumo is NOT taxable)
        taxable = rid_revenue[idx] + cer_tip[idx] + cer_cacv[idx]
        ires_irap[idx] = taxable * tax_rate

    logger.info(
        "Incentives computed: year 1 risparmio=%.0f, RID=%.0f, CER_TIP=%.0f, "
        "ammortamento=%.0f, tax=%.0f",
        risparmio_autoconsumo[0], rid_revenue[0], cer_tip[0],
        ammortamento[0], ires_irap[0],
    )

    return IncentiveResult(
        years=years,
        production_degraded=production_degraded,
        risparmio_autoconsumo=risparmio_autoconsumo,
        rid_revenue=rid_revenue,
        cer_tip=cer_tip,
        cer_cacv=cer_cacv,
        ammortamento=ammortamento,
        tax_shield=tax_shield,
        ires_irap=ires_irap,
    )
