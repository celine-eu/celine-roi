"""Shared test fixtures — synthetic 45 kWp Trentino reference case.

All expected values are hand-calculated in the design spec:
docs/superpowers/specs/2026-03-25-mvp-design.md
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from celine.roi.config_loader import load_config
from celine.roi.load_profiles import load_profile_config
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


PROFILE_PATH = CONFIG_DIR / "load_profiles" / "residential_default.json"


def _build_synthetic_hourly_production(annual_kwh: float) -> np.ndarray:
    """Build a synthetic 8760 hourly PV production array.

    Uses a simplified solar model: sinusoidal output between sunrise and sunset,
    varying with month (longer days in summer, shorter in winter).
    """
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    # Sunrise/sunset hours per month (approximate 46N latitude)
    sunrise = [7.5, 7.0, 6.5, 6.0, 5.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.0, 7.5]
    sunset = [16.5, 17.5, 18.5, 19.5, 20.5, 21.0, 21.0, 20.0, 19.0, 17.5, 16.5, 16.0]

    hourly = np.zeros(8760)
    offset = 0
    for month_idx, days in enumerate(days_per_month):
        sr = sunrise[month_idx]
        ss = sunset[month_idx]
        for _day in range(days):
            for hour in range(24):
                if sr <= hour < ss:
                    t_norm = (hour - sr) / (ss - sr)
                    hourly[offset + hour] = np.sin(np.pi * t_norm)
                else:
                    hourly[offset + hour] = 0.0
            offset += 24

    raw_total = hourly.sum()
    if raw_total > 0:
        hourly = hourly * (annual_kwh / raw_total)
    return hourly


@pytest.fixture()
def hourly_production() -> ProductionData:
    """Synthetic hourly production for 49,500 kWh/year."""
    annual = 49500.0
    hourly = _build_synthetic_hourly_production(annual)
    monthly = annual * SOLAR_MONTHLY_FRACTIONS
    return ProductionData(
        monthly_production_kwh=monthly,
        annual_production_kwh=annual,
        source="synthetic",
        hourly_production_kwh=hourly,
    )


@pytest.fixture()
def profile_config() -> dict:
    """PVGIS residential load profile config."""
    return load_profile_config(PROFILE_PATH)
