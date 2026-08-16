"""CAPEX estimator for PV installations.

Estimates system cost (pre-IVA) from number of panels and rooftop area
using a power law cost curve calibrated on Italian market data 2025-2026.

Panel specs and cost curve parameters live in config/panel_specs.yaml.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_panel_specs(specs_path: Path) -> dict[str, Any]:
    """Load panel specifications and cost curve from YAML config.

    Args:
        specs_path: Path to panel_specs.yaml.

    Returns:
        Dict with 'panel', 'cost_curve', and 'bounds' sections.

    Raises:
        FileNotFoundError: If specs_path does not exist.
        ValueError: If required keys are missing.
    """
    with open(specs_path) as fh:
        specs = yaml.safe_load(fh)

    required_sections = ["panel", "cost_curve", "bounds"]
    for section in required_sections:
        if section not in specs:
            raise ValueError(f"Missing required section '{section}' in panel specs")

    return specs


def max_panels_for_area(rooftop_area_m2: float, specs: dict[str, Any]) -> int:
    """Compute maximum panels that fit on a rooftop.

    Args:
        rooftop_area_m2: Available rooftop area in m².
        specs: Loaded panel specs config.

    Returns:
        Maximum number of panels (capped by max_kwp from config).
    """
    if rooftop_area_m2 <= 0:
        return 0

    panel_area = specs["panel"]["area_m2"]
    panel_wp = specs["panel"]["watt_peak"]
    max_kwp = specs["bounds"]["max_kwp"]

    max_by_area = math.floor(rooftop_area_m2 / panel_area)
    max_by_kwp = math.floor(max_kwp / (panel_wp / 1000))

    return min(max_by_area, max_by_kwp)


def estimate_capex(
    num_panels: int,
    rooftop_area_m2: float,
    specs: dict[str, Any],
) -> dict[str, float]:
    """Estimate system CAPEX from number of panels and rooftop area.

    Uses a power law cost curve: CAPEX = base_eur * kWp^exponent.

    Args:
        num_panels: Number of panels the user wants to install.
        rooftop_area_m2: Available rooftop area in m².
        specs: Loaded panel specs config.

    Returns:
        Dict with: num_panels, kwp, capex_eur, eur_per_kwp,
        rooftop_area_m2, max_panels, rooftop_utilization_pct.

    Raises:
        ValueError: If num_panels is below minimum or above maximum for the area.
    """
    min_panels = specs["bounds"]["min_panels"]
    max_panels = max_panels_for_area(rooftop_area_m2, specs)

    if num_panels < min_panels:
        raise ValueError(
            f"num_panels={num_panels} is below minimum ({min_panels} panels, "
            f"~{min_panels * specs['panel']['watt_peak'] / 1000:.1f} kWp)"
        )
    if num_panels > max_panels:
        raise ValueError(
            f"num_panels={num_panels} exceeds maximum for {rooftop_area_m2:.0f} m² "
            f"rooftop ({max_panels} panels, "
            f"~{max_panels * specs['panel']['watt_peak'] / 1000:.1f} kWp)"
        )

    panel_wp = specs["panel"]["watt_peak"]
    kwp = num_panels * panel_wp / 1000

    base = specs["cost_curve"]["base_eur"]
    exponent = specs["cost_curve"]["exponent"]
    floor = specs["cost_curve"]["floor_eur"]
    cap = specs["cost_curve"]["cap_eur"]

    capex = base * (kwp ** exponent)
    capex = max(floor, min(capex, cap))

    eur_per_kwp = capex / kwp
    panel_area = specs["panel"]["area_m2"]
    utilization = (num_panels * panel_area / rooftop_area_m2 * 100) if rooftop_area_m2 > 0 else 0.0

    logger.info(
        "CAPEX estimate: %d panels, %.1f kWp, %.0f EUR (%.0f EUR/kWp), %.1f%% rooftop used",
        num_panels, kwp, capex, eur_per_kwp, utilization,
    )

    return {
        "num_panels": num_panels,
        "kwp": kwp,
        "capex_eur": round(capex, 2),
        "eur_per_kwp": round(eur_per_kwp, 2),
        "rooftop_area_m2": rooftop_area_m2,
        "max_panels": max_panels,
        "rooftop_utilization_pct": round(utilization, 1),
    }
