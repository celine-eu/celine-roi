"""Shared test fixtures — synthetic 45 kWp Trentino reference case.

All expected values are hand-calculated in the design spec:
docs/superpowers/specs/2026-03-25-mvp-design.md
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from celine.roi.config_loader import load_config
from celine.roi.models import ProductionData, SystemInput

CONFIG_DIR = Path(__file__).parent.parent / "config"

# Normalized solar distribution for Trentino (46N latitude)
_RAW_SOLAR = [0.049, 0.059, 0.078, 0.098, 0.118, 0.127, 0.127, 0.118, 0.088, 0.069, 0.039, 0.029]
SOLAR_MONTHLY_FRACTIONS = np.array(_RAW_SOLAR) / sum(_RAW_SOLAR)


@pytest.fixture()
def config() -> dict:
    """Load config from project YAML files."""
    return load_config(CONFIG_DIR)


@pytest.fixture()
def reference_input() -> SystemInput:
    """Synthetic reference: 45 kWp, Lavarone, 100% equity, RID+CER."""
    return SystemInput(
        kwp=45.0,
        latitude=45.9333,
        longitude=11.2667,
        tilt=30.0,
        azimuth=0.0,
        capex=45000.0,
        annual_consumption_kwh=40000.0,
        user_type="commercial",
        regime="RID_CER",
        equity_fraction=1.0,
        loan_rate=0.0,
        loan_duration_years=0,
        annual_production_kwh=49500.0,
        location="Lavarone, Trentino",
    )


@pytest.fixture()
def reference_production() -> ProductionData:
    """Synthetic monthly production for 49,500 kWh/year."""
    annual = 49500.0
    monthly = annual * SOLAR_MONTHLY_FRACTIONS
    return ProductionData(
        monthly_production_kwh=monthly,
        annual_production_kwh=annual,
        source="synthetic",
    )
