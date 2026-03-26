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
