"""Finance engine for PV investment analysis.

Builds a 25-year discounted cash flow model and computes NPV, IRR,
payback periods, and DSCR from the incentive engine's yearly outputs.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import numpy_financial as npf

from celine.roi.models import FinanceResult, IncentiveResult, SystemInput

logger = logging.getLogger(__name__)

# Inverter replacement cost: power law with floor/cap
# Fit on Italian market data ~2025 for string inverters (installed)
_INVERTER_BASE = 180.0  # EUR/kWp at 1 kWp (intercept)
_INVERTER_ALPHA = 0.82  # sub-linear exponent (economies of scale)
_INVERTER_FLOOR = 1_200  # EUR minimum (labor + travel)
_INVERTER_CAP = 120_000  # EUR maximum (above this → central inverters)


def estimate_inverter_cost(kwp: float) -> float:
    """Estimate string inverter replacement cost (installed).

    Power law fit on Italian market data ~2025:
      10 kWp  → ~1,430 EUR  (143 EUR/kWp)
      78 kWp  → ~8,490 EUR  (109 EUR/kWp)
      200 kWp → ~15,800 EUR  (79 EUR/kWp)

    Args:
        kwp: System capacity in kWp.

    Returns:
        Estimated inverter replacement cost in EUR.
    """
    cost = _INVERTER_BASE * (kwp ** _INVERTER_ALPHA)
    return max(_INVERTER_FLOOR, min(cost, _INVERTER_CAP))


def compute_finance(
    system_input: SystemInput,
    incentive_result: IncentiveResult,
    config: dict[str, Any],
) -> FinanceResult:
    """Build 25-year cash flow and compute financial metrics.

    Args:
        system_input: System parameters (capex, financing).
        incentive_result: Yearly incentive calculations.
        config: Merged configuration dict.

    Returns:
        FinanceResult with cash flows, NPV, IRR, payback, and DSCR.
    """
    useful_life: int = config["useful_life"]
    capex: float = system_input.capex
    general_inflation: float = config["general_inflation"]
    om_base: float = config["om_per_kwp"] * system_input.kwp
    insurance_base: float = capex * config["insurance_rate"]
    inverter_year: int = config["inverter_replacement_year"]
    inverter_cost: float = estimate_inverter_cost(system_input.kwp)
    wacc: float = config["wacc"]

    equity_fraction: float = system_input.equity_fraction
    debt_principal: float = capex * (1.0 - equity_fraction)
    loan_duration: int = system_input.loan_duration_years
    if debt_principal > 0 and loan_duration > 0:
        annual_loan_payment = float(-npf.pmt(system_input.loan_rate, loan_duration, debt_principal))
    else:
        annual_loan_payment = 0.0

    cashflows = np.zeros(useful_life + 1)
    cashflows[0] = -capex * equity_fraction

    inc = incentive_result
    for idx in range(useful_life):
        year = idx + 1
        inflation_factor = (1.0 + general_inflation) ** (year - 1)

        # Only CER libero portion enters the producer's cashflow.
        # The vincolato portion is distributed to CER members.
        revenue = (
            inc.risparmio_autoconsumo[idx]
            + inc.rid_revenue[idx]
            + inc.cer_tip_libero[idx]
            + inc.cer_cacv_libero[idx]
            + inc.tax_shield[idx]
            + inc.detrazione_irpef[idx]
        )

        costs = inc.ires_irap[idx] + om_base * inflation_factor + insurance_base * inflation_factor

        if year <= loan_duration:
            costs += annual_loan_payment

        if year == inverter_year:
            costs += inverter_cost

        cashflows[year] = revenue - costs

    cumulative = np.cumsum(cashflows)
    npv = float(npf.npv(wacc, cashflows))
    irr = float(npf.irr(cashflows))

    payback_simple = _find_payback(cumulative)

    discount_factors = np.array([1.0 / (1.0 + wacc) ** t for t in range(useful_life + 1)])
    discounted_cf = cashflows * discount_factors
    cumulative_discounted = np.cumsum(discounted_cf)
    payback_discounted = _find_payback(cumulative_discounted)

    dscr: np.ndarray | None = None
    if annual_loan_payment > 0 and loan_duration > 0:
        dscr = np.zeros(loan_duration)
        for idx in range(loan_duration):
            year = idx + 1
            inflation_factor = (1.0 + general_inflation) ** (year - 1)
            operating_cf = (
                inc.risparmio_autoconsumo[idx]
                + inc.rid_revenue[idx]
                + inc.cer_tip_libero[idx]
                + inc.cer_cacv_libero[idx]
                + inc.tax_shield[idx]
                + inc.detrazione_irpef[idx]
                - inc.ires_irap[idx]
                - om_base * inflation_factor
                - insurance_base * inflation_factor
            )
            dscr[idx] = operating_cf / annual_loan_payment

    logger.info(
        "Finance: NPV=%.0f EUR, IRR=%.1f%%, payback_simple=%.1f yr, payback_disc=%.1f yr",
        npv, irr * 100, payback_simple, payback_discounted,
    )

    return FinanceResult(
        cashflows=cashflows,
        cumulative=cumulative,
        npv=npv,
        irr=irr,
        payback_simple=payback_simple,
        payback_discounted=payback_discounted,
        dscr=dscr,
    )


def _find_payback(cumulative: np.ndarray) -> float:
    """Find the payback period from cumulative cash flows.

    Returns the year (with linear interpolation) when cumulative first >= 0.
    If payback never occurs, returns inf.

    Args:
        cumulative: Array of cumulative cash flows (index 0 = year 0).

    Returns:
        Payback period in years as a float, or inf if never reached.
    """
    for idx in range(1, len(cumulative)):
        if cumulative[idx] >= 0:
            prev = cumulative[idx - 1]
            curr = cumulative[idx]
            fraction = -prev / (curr - prev) if curr != prev else 0.0
            return float(idx - 1 + fraction)
    return float("inf")
