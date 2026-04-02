"""Pipeline orchestrator for CELINE ROI scenarios.

Chains all engines: PVGIS → Energy → Incentives → Finance → Validation.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from celine.roi.engines.energy import compute_energy
from celine.roi.engines.finance import compute_finance
from celine.roi.engines.incentives import compute_incentives
from celine.roi.models import ScenarioResult, SystemInput
from celine.roi.pvgis_client import fetch_production
from celine.roi.validation.warnings import validate_model

logger = logging.getLogger(__name__)


def estimate_battery_cost(kwh: float, config: dict[str, Any]) -> float:
    """Estimate residential battery cost using a power law model.

    Fit on Italian market data 2025-2026 (Li-ion, installed):
      5 kWh  → ~5,500 EUR  (1,100 EUR/kWh)
     10 kWh  → ~8,100 EUR    (810 EUR/kWh)
     15 kWh  → ~10,050 EUR   (670 EUR/kWh)

    Args:
        kwh: Battery capacity in kWh.
        config: Configuration dict with battery_cost_base/exponent/floor.

    Returns:
        Estimated battery cost in EUR.
    """
    base: float = config.get("battery_cost_base", 2400.0)
    exponent: float = config.get("battery_cost_exponent", 0.53)
    floor: float = config.get("battery_cost_floor", 1500.0)
    return max(floor, base * (kwh ** exponent))


async def run_scenario(
    system_input: SystemInput,
    config: dict[str, Any],
) -> ScenarioResult:
    """Execute the full CELINE ROI pipeline.

    Args:
        system_input: System parameters and investment details.
        config: Merged configuration dict from YAML files.

    Returns:
        ScenarioResult with all intermediate and final results.
    """
    logger.info("Starting scenario: %s, %.1f kWp", system_input.location, system_input.kwp)

    # Battery cost deduction: subtract estimated battery cost from CAPEX
    # to isolate PV-only investment. No energy dispatch model yet.
    if system_input.battery_kwh > 0:
        battery_cost = estimate_battery_cost(system_input.battery_kwh, config)
        pv_capex = max(0.0, system_input.capex - battery_cost)
        logger.info(
            "Battery deduction: %.0f kWh → estimated %.0f EUR → "
            "PV CAPEX: %.0f EUR (was %.0f EUR)",
            system_input.battery_kwh, battery_cost,
            pv_capex, system_input.capex,
        )
        system_input = replace(system_input, capex=pv_capex)

    production_data = await fetch_production(system_input)
    logger.info(
        "Production: %.0f kWh/year (source: %s)",
        production_data.annual_production_kwh,
        production_data.source,
    )

    # If Trentino API provided a kWp from the rooftop polygon, use it
    # instead of the user-supplied value (which may be a guess)
    if production_data.effective_kwp is not None:
        if abs(production_data.effective_kwp - system_input.kwp) > 0.5:
            logger.info(
                "Overriding kWp: user=%.1f → Trentino API=%.1f (from rooftop polygon)",
                system_input.kwp,
                production_data.effective_kwp,
            )
        system_input = replace(system_input, kwp=production_data.effective_kwp)

    energy = compute_energy(system_input, production_data, config)
    incentives = compute_incentives(system_input, energy, config)
    finance = compute_finance(system_input, incentives, config)
    validation = validate_model(system_input, energy, incentives, finance, config)

    logger.info(
        "Scenario complete: NPV=%.0f EUR, IRR=%.1f%%, payback=%.1f yr | "
        "%d FAIL, %d WARN, %d PASS",
        finance.npv,
        finance.irr * 100,
        finance.payback_simple,
        len(validation.fails),
        len(validation.warns),
        len(validation.passes),
    )

    return ScenarioResult(
        system_input=system_input,
        production=production_data,
        energy=energy,
        incentives=incentives,
        finance=finance,
        validation=validation,
    )
