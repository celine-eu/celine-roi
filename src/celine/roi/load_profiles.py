"""Hourly load profile builder.

Generates 8760 hourly consumption values from annual consumption
and a normalized load profile (24h shape + monthly seasonal weights).

Profile data lives in config/load_profiles/*.json — never hardcoded.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

DAYS_PER_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
HOURS_PER_YEAR = sum(d * 24 for d in DAYS_PER_MONTH)  # 8760


def load_profile_config(profile_path: Path) -> dict[str, Any]:
    """Load a JSON load profile configuration.

    Args:
        profile_path: Path to the profile JSON file.

    Returns:
        Dict with 'hourly_coefficients' (24 floats) and
        'monthly_weights' (12 floats), both normalized to sum=1.0.

    Raises:
        FileNotFoundError: If profile_path does not exist.
        ValueError: If coefficients don't validate.
    """
    with open(profile_path) as fh:
        config = json.load(fh)

    hourly = config["hourly_coefficients"]
    monthly = config["monthly_weights"]

    if len(hourly) != 24:
        raise ValueError(f"Expected 24 hourly coefficients, got {len(hourly)}")
    if len(monthly) != 12:
        raise ValueError(f"Expected 12 monthly weights, got {len(monthly)}")
    if abs(sum(hourly) - 1.0) > 0.01:
        raise ValueError(f"Hourly coefficients sum to {sum(hourly)}, expected 1.0")
    if abs(sum(monthly) - 1.0) > 0.01:
        raise ValueError(f"Monthly weights sum to {sum(monthly)}, expected 1.0")

    return config


def build_hourly_consumption(
    annual_consumption_kwh: float,
    profile_config: dict[str, Any],
) -> np.ndarray:
    """Build 8760 hourly consumption array from annual total and load profile.

    Algorithm:
    1. Distribute annual consumption across months using monthly_weights.
    2. Within each month, distribute daily consumption using hourly_coefficients.
    3. Result: 8760 hourly kWh values that sum to annual_consumption_kwh.

    Args:
        annual_consumption_kwh: Total annual electricity consumption in kWh.
        profile_config: Loaded profile config with hourly_coefficients and
            monthly_weights.

    Returns:
        Numpy array of shape (8760,) with hourly consumption in kWh.
    """
    if annual_consumption_kwh == 0.0:
        return np.zeros(HOURS_PER_YEAR)

    hourly_shape = np.array(profile_config["hourly_coefficients"])
    monthly_weights = np.array(profile_config["monthly_weights"])

    result = np.zeros(HOURS_PER_YEAR)
    offset = 0

    for month_idx, days in enumerate(DAYS_PER_MONTH):
        monthly_kwh = annual_consumption_kwh * monthly_weights[month_idx]
        daily_kwh = monthly_kwh / days

        for _day in range(days):
            result[offset : offset + 24] = daily_kwh * hourly_shape
            offset += 24

    logger.info(
        "Built hourly consumption profile: %.0f kWh/year, peak hour=%.3f kWh",
        result.sum(),
        result.max(),
    )

    return result
