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

    try:
        hourly = config["hourly_coefficients"]
        monthly = config["monthly_weights"]
    except KeyError as exc:
        raise ValueError(f"Missing required key in profile config: {exc}") from exc

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
    if annual_consumption_kwh < 0:
        raise ValueError(
            f"annual_consumption_kwh must be >= 0, got {annual_consumption_kwh}"
        )
    if annual_consumption_kwh == 0.0:
        return np.zeros(HOURS_PER_YEAR)

    hourly_shape = np.array(profile_config["hourly_coefficients"])
    monthly_weights = np.array(profile_config["monthly_weights"])

    result = np.zeros(HOURS_PER_YEAR)
    offset = 0

    for month_idx, days in enumerate(DAYS_PER_MONTH):
        monthly_kwh = annual_consumption_kwh * monthly_weights[month_idx]
        daily_kwh = monthly_kwh / days
        month_slice = np.tile(hourly_shape * daily_kwh, days)
        result[offset : offset + days * 24] = month_slice
        offset += days * 24

    logger.info(
        "Built hourly consumption profile: %.0f kWh/year, peak hour=%.3f kWh",
        result.sum(),
        result.max(),
    )

    return result


def profile_from_manual_hourly(hourly_kwh: tuple[float, ...] | list[float]) -> dict[str, Any]:
    """Build a profile config from 24 user-provided mean kWh/hour values.

    The values represent the user's average consumption for each hour of the
    day in kWh.  They are normalized to sum=1.0 for hourly_coefficients and
    paired with flat monthly weights (no seasonal variation).

    Args:
        hourly_kwh: 24 mean kWh values, one per hour (00:00-23:00).

    Returns:
        Profile config dict compatible with build_hourly_consumption().

    Raises:
        ValueError: If not exactly 24 values or all zeros.
    """
    if len(hourly_kwh) != 24:
        raise ValueError(f"Expected 24 hourly values, got {len(hourly_kwh)}")

    total = sum(hourly_kwh)
    if total <= 0:
        raise ValueError("Hourly values must sum to a positive number")

    coefficients = [v / total for v in hourly_kwh]
    monthly_weights = [1.0 / 12] * 12

    return {
        "profile_type": "manual_24h",
        "hourly_coefficients": coefficients,
        "monthly_weights": monthly_weights,
    }


def load_meter_data_profile(folder_path: Path) -> dict[str, Any]:
    """Build a profile config from a folder of daily smart-meter JSON files.

    Each file is named YYYY-MM-DD.json and contains hourly consumption in
    the C2G/e-distribuzione format:
        {"imported": {"data": {"consumptions": [{"hour": 0, "total": ...}, ...]}}}

    The function computes average hourly coefficients and monthly weights
    from all available data.

    Args:
        folder_path: Path to the meter data folder.

    Returns:
        Profile config dict compatible with build_hourly_consumption().

    Raises:
        FileNotFoundError: If folder does not exist.
        ValueError: If no valid data found.
    """
    if not folder_path.is_dir():
        raise FileNotFoundError(f"Meter data folder not found: {folder_path}")

    # Accumulate hourly totals per month: {month_1based: [sum_h0..sum_h23]}
    monthly_hourly_sums: dict[int, list[float]] = {}
    monthly_day_counts: dict[int, int] = {}

    json_files = sorted(folder_path.glob("*.json"))
    if not json_files:
        raise ValueError(f"No JSON files found in {folder_path}")

    for json_file in json_files:
        try:
            with open(json_file) as fh:
                data = json.load(fh)

            consumptions = data["imported"]["data"]["consumptions"]
            if not consumptions:
                continue

            month = consumptions[0].get("month")
            if month is None:
                continue

            if month not in monthly_hourly_sums:
                monthly_hourly_sums[month] = [0.0] * 24
                monthly_day_counts[month] = 0

            for entry in consumptions:
                hour = entry.get("hour")
                total = entry.get("total", 0.0)
                if hour is not None and 0 <= hour < 24 and total is not None:
                    monthly_hourly_sums[month][hour] += float(total)

            monthly_day_counts[month] += 1

        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Skipping invalid meter file: %s", json_file.name)
            continue

    if not monthly_hourly_sums:
        raise ValueError(f"No valid meter data found in {folder_path}")

    # Compute average daily hourly profile (across all months)
    hourly_totals = np.zeros(24)
    total_days = 0
    for month, sums in monthly_hourly_sums.items():
        hourly_totals += np.array(sums)
        total_days += monthly_day_counts[month]

    if hourly_totals.sum() <= 0:
        raise ValueError("Meter data contains zero total consumption")

    # Normalize hourly coefficients (average day shape)
    hourly_avg = hourly_totals / total_days
    hourly_coefficients = (hourly_avg / hourly_avg.sum()).tolist()

    # Compute monthly weights from actual monthly totals
    monthly_totals = np.zeros(12)
    for month, sums in monthly_hourly_sums.items():
        monthly_totals[month - 1] = sum(sums)

    # Fill missing months with average of available months
    available_months = monthly_totals > 0
    if available_months.any():
        avg_monthly = monthly_totals[available_months].mean()
        monthly_totals[~available_months] = avg_monthly

    monthly_weights = (monthly_totals / monthly_totals.sum()).tolist()

    logger.info(
        "Loaded meter data profile from %s: %d files, %d months, "
        "%.1f kWh/day avg",
        folder_path.name, len(json_files), len(monthly_hourly_sums),
        hourly_avg.sum(),
    )

    return {
        "profile_type": "meter_data",
        "source_folder": folder_path.name,
        "days_loaded": total_days,
        "months_covered": sorted(monthly_hourly_sums.keys()),
        "daily_avg_kwh": round(float(hourly_avg.sum()), 3),
        "hourly_coefficients": hourly_coefficients,
        "monthly_weights": monthly_weights,
    }


def build_hourly_consumption_with_heat_pump(
    annual_consumption_kwh: float,
    base_profile_config: dict[str, Any],
    heat_pump_kwh_annual: float,
    heat_pump_profile_config: dict[str, Any],
) -> np.ndarray:
    """Build 8760 hourly consumption array blending a base profile with a heat pump component.

    The heat pump load is built separately from its own profile (daytime-heavy) then
    added to the base consumption. This works for any base user_type profile.

    Args:
        annual_consumption_kwh: Base annual consumption in kWh (excluding heat pump).
        base_profile_config: Loaded profile config for the user_type (hourly + monthly).
        heat_pump_kwh_annual: Additional annual electricity consumed by the heat pump in kWh.
        heat_pump_profile_config: Loaded heat pump component profile config.

    Returns:
        Numpy array of shape (8760,) summing to annual_consumption_kwh + heat_pump_kwh_annual.
    """
    base = build_hourly_consumption(annual_consumption_kwh, base_profile_config)
    hp = build_hourly_consumption(heat_pump_kwh_annual, heat_pump_profile_config)
    return base + hp
