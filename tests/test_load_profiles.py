"""Tests for the hourly load profile builder module.

Run with: pytest tests/test_load_profiles.py -v
"""

import json
from pathlib import Path

import numpy as np
import pytest

from celine.roi.load_profiles import (
    build_hourly_consumption,
    build_hourly_consumption_with_heat_pump,
    load_profile_config,
)

CONFIG_DIR = Path(__file__).parent.parent / "config"
PROFILE_PATH = CONFIG_DIR / "load_profiles" / "residential_default.json"

DAYS_PER_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


class TestLoadProfileConfig:
    """Tests for load_profile_config().

    @verifies REQ-0802
    """

    def test_load_profile_config(self) -> None:
        """Loads config and checks required keys exist."""
        config = load_profile_config(PROFILE_PATH)
        assert "hourly_coefficients" in config
        assert "monthly_weights" in config

    def test_hourly_coefficients_sum_to_one(self) -> None:
        """24 hourly coefficients must sum to approximately 1.0."""
        config = load_profile_config(PROFILE_PATH)
        coefficients = config["hourly_coefficients"]
        assert len(coefficients) == 24
        assert abs(sum(coefficients) - 1.0) < 1e-6

    def test_monthly_weights_sum_to_one(self) -> None:
        """12 monthly weights must sum to approximately 1.0."""
        config = load_profile_config(PROFILE_PATH)
        weights = config["monthly_weights"]
        assert len(weights) == 12
        assert abs(sum(weights) - 1.0) < 1e-6


class TestBuildHourlyConsumption:
    """Tests for build_hourly_consumption().

    @verifies REQ-0803
    """

    @pytest.fixture()
    def profile_config(self) -> dict:
        """Load the residential default profile config."""
        return load_profile_config(PROFILE_PATH)

    def test_returns_8760_array(self, profile_config: dict) -> None:
        """Result must be a numpy array of length 8760."""
        result = build_hourly_consumption(3000.0, profile_config)
        assert isinstance(result, np.ndarray)
        assert len(result) == 8760

    def test_annual_total_preserved(self, profile_config: dict) -> None:
        """Sum of hourly values must equal the annual input."""
        annual_kwh = 4500.0
        result = build_hourly_consumption(annual_kwh, profile_config)
        assert abs(result.sum() - annual_kwh) < 1e-6

    def test_all_values_non_negative(self, profile_config: dict) -> None:
        """No hourly value should be negative."""
        result = build_hourly_consumption(3000.0, profile_config)
        assert np.all(result >= 0.0)

    def test_nighttime_higher_than_midday(self, profile_config: dict) -> None:
        """Evening hours (20-23) average should be > midday (9-13) average * 2.

        The PVGIS residential profile has a strong evening peak; this reflects
        that household consumption is minimal at solar noon.
        """
        result = build_hourly_consumption(3000.0, profile_config)
        # Use first week (168 hours) to sample daily pattern stably
        first_week = result[:168]

        evening_hours = [20, 21, 22, 23]
        midday_hours = [9, 10, 11, 12]

        evening_avg = np.mean([first_week[h::24] for h in evening_hours])
        midday_avg = np.mean([first_week[h::24] for h in midday_hours])

        assert evening_avg > midday_avg * 2

    def test_winter_higher_than_summer(self, profile_config: dict) -> None:
        """January total consumption should be higher than July total.

        January monthly weight (0.098) > July monthly weight (0.067).
        """
        result = build_hourly_consumption(3000.0, profile_config)
        # January: hours 0–743
        january_hours = 0
        for _m in range(0):
            january_hours += DAYS_PER_MONTH[_m] * 24
        january_end = january_hours + DAYS_PER_MONTH[0] * 24

        # July: month index 6, hours 4344–5087
        july_start = sum(d * 24 for d in DAYS_PER_MONTH[:6])
        july_end = july_start + DAYS_PER_MONTH[6] * 24

        january_total = result[january_hours:january_end].sum()
        july_total = result[july_start:july_end].sum()

        assert january_total > july_total

    def test_zero_consumption(self, profile_config: dict) -> None:
        """Zero annual consumption returns 8760 zeros."""
        result = build_hourly_consumption(0.0, profile_config)
        assert isinstance(result, np.ndarray)
        assert len(result) == 8760
        assert np.all(result == 0.0)

    def test_monthly_distribution_matches_weights(self, profile_config: dict) -> None:
        """Each month's share of total consumption must match config weights."""
        annual_kwh = 10000.0
        result = build_hourly_consumption(annual_kwh, profile_config)
        monthly_weights = profile_config["monthly_weights"]

        offset = 0
        for month_idx, days in enumerate(DAYS_PER_MONTH):
            month_hours = days * 24
            month_total = result[offset : offset + month_hours].sum()
            expected = annual_kwh * monthly_weights[month_idx]
            assert abs(month_total - expected) < 1e-6, (
                f"Month {month_idx + 1}: got {month_total:.4f}, expected {expected:.4f}"
            )
            offset += month_hours


class TestLoadProfileConfigErrors:
    """Tests for error handling in profile config loading.

    @verifies REQ-0802
    """

    def test_missing_hourly_coefficients_raises(self, tmp_path: Path) -> None:
        config = {"monthly_weights": [1 / 12] * 12}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match="Missing required key"):
            load_profile_config(path)

    def test_missing_monthly_weights_raises(self, tmp_path: Path) -> None:
        config = {"hourly_coefficients": [1 / 24] * 24}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match="Missing required key"):
            load_profile_config(path)

    def test_wrong_hourly_count_raises(self, tmp_path: Path) -> None:
        config = {"hourly_coefficients": [0.5, 0.5], "monthly_weights": [1 / 12] * 12}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match="Expected 24"):
            load_profile_config(path)

    def test_negative_consumption_raises(self) -> None:
        config = load_profile_config(PROFILE_PATH)
        with pytest.raises(ValueError, match="must be >= 0"):
            build_hourly_consumption(-100.0, config)


HP_PROFILE_PATH = CONFIG_DIR / "load_profiles" / "heat_pump_component.json"


class TestBuildHourlyConsumptionWithHeatPump:
    """Tests for build_hourly_consumption_with_heat_pump().

    @verifies REQ-0108
    """

    @pytest.fixture()
    def residential_config(self) -> dict:
        return load_profile_config(PROFILE_PATH)

    @pytest.fixture()
    def hp_config(self) -> dict:
        return load_profile_config(HP_PROFILE_PATH)

    def test_total_sum_equals_base_plus_hp(
        self, residential_config: dict, hp_config: dict
    ) -> None:
        """Result must sum to base_kwh + heat_pump_kwh."""
        base_kwh = 3000.0
        hp_kwh = 3500.0
        result = build_hourly_consumption_with_heat_pump(
            base_kwh, residential_config, hp_kwh, hp_config
        )
        assert abs(result.sum() - (base_kwh + hp_kwh)) < 0.01

    def test_returns_8760_array(
        self, residential_config: dict, hp_config: dict
    ) -> None:
        result = build_hourly_consumption_with_heat_pump(
            3000.0, residential_config, 3500.0, hp_config
        )
        assert isinstance(result, np.ndarray)
        assert len(result) == 8760

    def test_zero_hp_kwh_equals_base_only(
        self, residential_config: dict, hp_config: dict
    ) -> None:
        """With heat_pump_kwh=0, result must equal plain build_hourly_consumption."""
        base_kwh = 3000.0
        base_only = build_hourly_consumption(base_kwh, residential_config)
        with_hp = build_hourly_consumption_with_heat_pump(
            base_kwh, residential_config, 0.0, hp_config
        )
        np.testing.assert_allclose(with_hp, base_only)

    def test_hp_shifts_daytime_share_upward(
        self, residential_config: dict, hp_config: dict
    ) -> None:
        """Adding HP (daytime-heavy) must increase the share of consumption in solar hours (8-18).

        Residential default is evening-heavy so solar hours share is low.
        HP component is daytime-heavy so blending must raise that share.
        """
        base_kwh = 3000.0
        hp_kwh = 3500.0
        base_only = build_hourly_consumption(base_kwh, residential_config)
        with_hp = build_hourly_consumption_with_heat_pump(
            base_kwh, residential_config, hp_kwh, hp_config
        )
        # Solar hours: 08:00–18:00 (indices 8–17 in each 24h day)
        solar_indices = list(range(8, 18))
        first_week = 7 * 24

        base_solar = sum(base_only[:first_week][h::24].sum() for h in solar_indices)
        hp_solar = sum(with_hp[:first_week][h::24].sum() for h in solar_indices)

        base_share = base_solar / base_only[:first_week].sum()
        hp_share = hp_solar / with_hp[:first_week].sum()

        assert hp_share > base_share, (
            f"HP blend solar share ({hp_share:.2%}) should exceed "
            f"residential base ({base_share:.2%})"
        )
