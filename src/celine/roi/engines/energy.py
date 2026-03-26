"""Energy matching engine.

Computes self-consumption (autoconsumo), grid feed-in (immissione),
grid withdrawal (prelievo), and CER shared energy for each period.

The engine operates on numpy arrays of any length:
- 12 elements for monthly resolution (MVP)
- 8760 elements for hourly resolution (V1)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from celine.roi.models import EnergyResult, ProductionData, SystemInput

logger = logging.getLogger(__name__)


def compute_energy(
    system_input: SystemInput,
    production_data: ProductionData,
    config: dict[str, Any],
) -> EnergyResult:
    """Match PV production against consumption to compute energy flows.

    Args:
        system_input: System parameters (consumption, regime).
        production_data: Monthly production array from PVGIS or synthetic.
        config: Merged configuration dict (needs sharing_ratio).

    Returns:
        EnergyResult with per-period arrays and self-consumption ratio.
    """
    production = production_data.monthly_production_kwh.copy()
    num_periods = len(production)

    # L1 consumption: flat distribution
    consumption = np.full(num_periods, system_input.annual_consumption_kwh / num_periods)

    # Energy matching per period
    autoconsumo = np.minimum(production, consumption)
    immissione = production - autoconsumo
    prelievo = consumption - autoconsumo

    # CER shared energy
    sharing_ratio = config["sharing_ratio"]
    energia_condivisa = immissione * sharing_ratio

    # Self-consumption ratio
    total_production = production.sum()
    tasso_autoconsumo = float(autoconsumo.sum() / total_production) if total_production > 0 else 0.0

    # Invariant check
    balance_error = abs(autoconsumo.sum() + immissione.sum() - total_production)
    assert balance_error < 0.01, (
        f"Energy balance violated: autoconsumo + immissione = "
        f"{autoconsumo.sum() + immissione.sum():.2f}, production = {total_production:.2f}"
    )

    logger.info(
        "Energy matching: production=%.0f kWh, autoconsumo=%.0f kWh (%.1f%%), "
        "immissione=%.0f kWh, condivisa=%.0f kWh",
        total_production, autoconsumo.sum(), tasso_autoconsumo * 100,
        immissione.sum(), energia_condivisa.sum(),
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
