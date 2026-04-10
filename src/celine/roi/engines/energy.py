"""Energy matching engine.

Computes self-consumption (autoconsumo), grid feed-in (immissione),
grid withdrawal (prelievo), and CER shared energy for each period.

Supports two modes:
- L1 (monthly): flat consumption, 12-element arrays (fallback)
- L2 (hourly): PVGIS load profile, 8760-element arrays (default when hourly data available)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from celine.roi.load_profiles import (
    build_hourly_consumption,
    build_hourly_consumption_with_heat_pump,
    load_meter_data_profile,
    load_profile_config,
    profile_from_manual_hourly,
)
from celine.roi.models import EnergyResult, ProductionData, SystemInput

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(os.environ.get("CELINE_CONFIG_DIR", "config"))


def compute_energy(
    system_input: SystemInput,
    production_data: ProductionData,
    config: dict[str, Any],
) -> EnergyResult:
    """Match PV production against consumption to compute energy flows.

    When hourly production data is available, uses L2 hourly matching with
    a load profile for realistic self-consumption. Falls back to L1 flat
    monthly matching otherwise.

    Args:
        system_input: System parameters (consumption, regime).
        production_data: Production data from PVGIS or synthetic.
        config: Merged configuration dict (needs sharing_ratio).

    Returns:
        EnergyResult with per-period arrays and self-consumption ratio.
    """
    if production_data.hourly_production_kwh is not None:
        return _compute_hourly(system_input, production_data, config)
    return _compute_monthly(system_input, production_data, config)


def _compute_monthly(
    system_input: SystemInput,
    production_data: ProductionData,
    config: dict[str, Any],
) -> EnergyResult:
    """L1 flat monthly matching (original behavior)."""
    production = production_data.monthly_production_kwh.copy()
    num_periods = len(production)

    consumption = np.full(num_periods, system_input.annual_consumption_kwh / num_periods)

    return _match_and_build_result(production, consumption, config)


def _compute_hourly(
    system_input: SystemInput,
    production_data: ProductionData,
    config: dict[str, Any],
) -> EnergyResult:
    """L2 hourly matching with load profile."""
    production = production_data.hourly_production_kwh.copy()

    if len(production) != 8760:
        raise ValueError(
            f"hourly_production_kwh must have 8760 elements, got {len(production)}"
        )

    # Profile selection priority:
    # 1. custom_hourly_kwh (manual 24h values from webapp)
    # 2. custom_profile_dir (smart meter data folder)
    # 3. user_type-based profile from config
    if system_input.custom_hourly_kwh is not None:
        profile_config = profile_from_manual_hourly(system_input.custom_hourly_kwh)
        logger.info("Using manual 24h consumption profile")
    elif system_input.custom_profile_dir is not None:
        meter_path = _CONFIG_DIR / "load_profiles" / system_input.custom_profile_dir
        profile_config = load_meter_data_profile(meter_path)
        logger.info("Using meter data profile from %s", system_input.custom_profile_dir)
    else:
        profile_map = config.get("load_profile_by_type", {})
        profile_name = profile_map.get(
            system_input.user_type,
            config.get("load_profile", "residential_default.json"),
        )
        profile_path = _CONFIG_DIR / "load_profiles" / profile_name

        if not profile_path.exists():
            raise FileNotFoundError(
                f"Load profile not found: {profile_path}. "
                "Set 'load_profile' in config or check config directory."
            )
        profile_config = load_profile_config(profile_path)

    if system_input.heat_pump_kwh_annual > 0:
        hp_profile_name = config.get("heat_pump_profile", "heat_pump_component.json")
        hp_profile_path = _CONFIG_DIR / "load_profiles" / hp_profile_name
        if not hp_profile_path.exists():
            raise FileNotFoundError(
                f"Heat pump component profile not found: {hp_profile_path}"
            )
        hp_profile_config = load_profile_config(hp_profile_path)
        consumption = build_hourly_consumption_with_heat_pump(
            annual_consumption_kwh=system_input.annual_consumption_kwh,
            base_profile_config=profile_config,
            heat_pump_kwh_annual=system_input.heat_pump_kwh_annual,
            heat_pump_profile_config=hp_profile_config,
        )
    else:
        consumption = build_hourly_consumption(
            annual_consumption_kwh=system_input.annual_consumption_kwh,
            profile_config=profile_config,
        )

    return _match_and_build_result(production, consumption, config)


def _match_and_build_result(
    production: np.ndarray,
    consumption: np.ndarray,
    config: dict[str, Any],
) -> EnergyResult:
    """Core energy matching logic shared by L1 and L2 modes.

    Args:
        production: Per-period production in kWh (12 or 8760 elements).
        consumption: Per-period consumption in kWh (same length as production).
        config: Configuration dict containing sharing_ratio.

    Returns:
        EnergyResult with matched energy flows.
    """
    autoconsumo = np.minimum(production, consumption)
    immissione = production - autoconsumo
    prelievo = consumption - autoconsumo

    sharing_ratio = config["sharing_ratio"]
    cer_virtual_rate = config.get("cer_virtual_consumption_rate", 1.0)
    energia_condivisa = immissione * sharing_ratio * cer_virtual_rate

    total_production = production.sum()
    tasso_autoconsumo = float(autoconsumo.sum() / total_production) if total_production > 0 else 0.0

    # Invariant check
    balance_error = abs(autoconsumo.sum() + immissione.sum() - total_production)
    if balance_error >= 0.01:
        raise ValueError(
            f"Energy balance violated: autoconsumo + immissione = "
            f"{autoconsumo.sum() + immissione.sum():.4f}, production = {total_production:.4f}"
        )

    mode = "L2 hourly" if len(production) > 12 else "L1 monthly"
    logger.info(
        "Energy matching (%s): production=%.0f kWh, autoconsumo=%.0f kWh (%.1f%%), "
        "immissione=%.0f kWh, prelievo=%.0f kWh, condivisa=%.0f kWh",
        mode, total_production, autoconsumo.sum(), tasso_autoconsumo * 100,
        immissione.sum(), prelievo.sum(), energia_condivisa.sum(),
    )

    return EnergyResult(
        production=production,
        consumption=consumption,
        autoconsumo=autoconsumo,
        immissione=immissione,
        prelievo=prelievo,
        energia_condivisa=energia_condivisa,
        tasso_autoconsumo=tasso_autoconsumo,
    )
