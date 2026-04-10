"""Tests for custom personal consumption profiles.

Covers:
- Manual 24h kWh input (profile_from_manual_hourly)
- Meter data folder loading (load_meter_data_profile)
- Energy engine integration (custom profiles override user_type default)
- Full pipeline with custom profiles
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from celine.roi.config_loader import load_config
from celine.roi.engines.energy import compute_energy
from celine.roi.load_profiles import (
    build_hourly_consumption,
    load_meter_data_profile,
    profile_from_manual_hourly,
)
from celine.roi.models import ProductionData, SystemInput

CONFIG_DIR = Path(__file__).parent.parent / "config"
LOAD_PROFILES_DIR = CONFIG_DIR / "load_profiles"
METER_DATA_DIR = LOAD_PROFILES_DIR / "IT221E00549903"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def config() -> dict[str, Any]:
    return load_config(CONFIG_DIR)


@pytest.fixture()
def base_system_input() -> SystemInput:
    return SystemInput(
        kwp=6.0,
        latitude=46.07,
        longitude=11.12,
        tilt=30,
        azimuth=0,
        capex=8400,
        annual_consumption_kwh=4500,
        user_type="residential",
        regime="RID_CER",
        equity_fraction=1.0,
        loan_rate=0.0,
        loan_duration_years=0,
        annual_production_kwh=7200,
    )


@pytest.fixture()
def synthetic_production() -> ProductionData:
    """Synthetic hourly production for testing."""
    from celine.roi.pvgis_client import _build_synthetic_hourly

    annual = 7200.0
    hourly = _build_synthetic_hourly(annual)
    monthly_fractions = np.array(
        [0.049, 0.059, 0.078, 0.098, 0.118, 0.127,
         0.127, 0.118, 0.088, 0.069, 0.039, 0.029]
    )
    monthly_fractions = monthly_fractions / monthly_fractions.sum()
    return ProductionData(
        monthly_production_kwh=annual * monthly_fractions,
        annual_production_kwh=annual,
        source="synthetic",
        hourly_production_kwh=hourly,
    )


FLAT_24H = [0.2] * 24  # 0.2 kWh each hour = 4.8 kWh/day
EVENING_PEAK_24H = [
    0.1, 0.08, 0.05, 0.05, 0.05, 0.06,
    0.08, 0.1, 0.12, 0.15, 0.15, 0.18,
    0.2, 0.22, 0.2, 0.18, 0.15, 0.2,
    0.25, 0.35, 0.5, 0.6, 0.4, 0.2,
]


# ── profile_from_manual_hourly ────────────────────────────────────────────────


class TestManualProfile:
    """Tests for profile_from_manual_hourly()."""

    def test_flat_profile_coefficients_equal(self) -> None:
        profile = profile_from_manual_hourly(FLAT_24H)
        coefficients = profile["hourly_coefficients"]
        assert len(coefficients) == 24
        assert all(abs(c - 1 / 24) < 1e-10 for c in coefficients)

    def test_flat_profile_monthly_weights_equal(self) -> None:
        profile = profile_from_manual_hourly(FLAT_24H)
        weights = profile["monthly_weights"]
        assert len(weights) == 12
        assert all(abs(w - 1 / 12) < 1e-10 for w in weights)

    def test_coefficients_sum_to_one(self) -> None:
        profile = profile_from_manual_hourly(EVENING_PEAK_24H)
        assert abs(sum(profile["hourly_coefficients"]) - 1.0) < 1e-10

    def test_weights_sum_to_one(self) -> None:
        profile = profile_from_manual_hourly(EVENING_PEAK_24H)
        assert abs(sum(profile["monthly_weights"]) - 1.0) < 1e-10

    def test_peak_hour_preserved(self) -> None:
        profile = profile_from_manual_hourly(EVENING_PEAK_24H)
        coefficients = profile["hourly_coefficients"]
        peak_idx = coefficients.index(max(coefficients))
        original_peak = EVENING_PEAK_24H.index(max(EVENING_PEAK_24H))
        assert peak_idx == original_peak

    def test_wrong_length_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected 24"):
            profile_from_manual_hourly([0.1] * 12)

    def test_all_zeros_raises(self) -> None:
        with pytest.raises(ValueError, match="positive number"):
            profile_from_manual_hourly([0.0] * 24)

    def test_build_consumption_matches_annual(self) -> None:
        profile = profile_from_manual_hourly(EVENING_PEAK_24H)
        consumption = build_hourly_consumption(4500.0, profile)
        assert len(consumption) == 8760
        assert abs(consumption.sum() - 4500.0) < 0.1

    def test_profile_type_set(self) -> None:
        profile = profile_from_manual_hourly(FLAT_24H)
        assert profile["profile_type"] == "manual_24h"

    def test_tuple_input_works(self) -> None:
        profile = profile_from_manual_hourly(tuple(FLAT_24H))
        assert len(profile["hourly_coefficients"]) == 24


# ── load_meter_data_profile ───────────────────────────────────────────────────


class TestMeterDataProfile:
    """Tests for load_meter_data_profile()."""

    @pytest.mark.skipif(
        not METER_DATA_DIR.is_dir(),
        reason="Meter data folder not available",
    )
    def test_loads_real_meter_data(self) -> None:
        profile = load_meter_data_profile(METER_DATA_DIR)
        assert len(profile["hourly_coefficients"]) == 24
        assert len(profile["monthly_weights"]) == 12
        assert abs(sum(profile["hourly_coefficients"]) - 1.0) < 0.01
        assert abs(sum(profile["monthly_weights"]) - 1.0) < 0.01

    @pytest.mark.skipif(
        not METER_DATA_DIR.is_dir(),
        reason="Meter data folder not available",
    )
    def test_daily_avg_positive(self) -> None:
        profile = load_meter_data_profile(METER_DATA_DIR)
        assert profile["daily_avg_kwh"] > 0

    @pytest.mark.skipif(
        not METER_DATA_DIR.is_dir(),
        reason="Meter data folder not available",
    )
    def test_months_covered(self) -> None:
        profile = load_meter_data_profile(METER_DATA_DIR)
        assert len(profile["months_covered"]) >= 1

    @pytest.mark.skipif(
        not METER_DATA_DIR.is_dir(),
        reason="Meter data folder not available",
    )
    def test_build_consumption_from_meter_profile(self) -> None:
        profile = load_meter_data_profile(METER_DATA_DIR)
        consumption = build_hourly_consumption(3500.0, profile)
        assert len(consumption) == 8760
        assert abs(consumption.sum() - 3500.0) < 0.1

    def test_nonexistent_folder_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_meter_data_profile(Path("/nonexistent/folder"))

    def test_empty_folder_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No JSON files"):
            load_meter_data_profile(tmp_path)

    def test_synthetic_meter_folder(self, tmp_path: Path) -> None:
        """Build a small synthetic meter data folder and verify loading."""
        for day in range(1, 4):
            consumptions = []
            for hour in range(24):
                consumptions.append({
                    "hour": hour,
                    "month": 1,
                    "day": day,
                    "year": 2025,
                    "total": 0.1 + 0.02 * hour,
                })
            data = {
                "imported": {
                    "data": {
                        "consumptions": consumptions,
                        "total": sum(c["total"] for c in consumptions),
                    }
                }
            }
            (tmp_path / f"2025-01-{day:02d}.json").write_text(json.dumps(data))

        profile = load_meter_data_profile(tmp_path)
        assert len(profile["hourly_coefficients"]) == 24
        assert abs(sum(profile["hourly_coefficients"]) - 1.0) < 0.01
        assert profile["days_loaded"] == 3
        assert 1 in profile["months_covered"]

    def test_profile_type_set(self, tmp_path: Path) -> None:
        """Verify profile_type is 'meter_data'."""
        consumptions = [{"hour": h, "month": 3, "total": 0.5} for h in range(24)]
        data = {"imported": {"data": {"consumptions": consumptions}}}
        (tmp_path / "2025-03-01.json").write_text(json.dumps(data))

        profile = load_meter_data_profile(tmp_path)
        assert profile["profile_type"] == "meter_data"


# ── Energy engine integration ─────────────────────────────────────────────────


class TestEnergyCustomProfile:
    """Test that custom profiles are used by the energy engine."""

    def test_manual_profile_overrides_default(
        self,
        base_system_input: SystemInput,
        synthetic_production: ProductionData,
        config: dict[str, Any],
    ) -> None:
        from dataclasses import replace

        si_custom = replace(
            base_system_input,
            custom_hourly_kwh=tuple(EVENING_PEAK_24H),
        )

        result_default = compute_energy(base_system_input, synthetic_production, config)
        result_custom = compute_energy(si_custom, synthetic_production, config)

        # Self-consumption should differ because profiles differ
        assert result_default.tasso_autoconsumo != result_custom.tasso_autoconsumo

        # Energy balance must still hold
        assert abs(
            result_custom.autoconsumo.sum() + result_custom.immissione.sum()
            - result_custom.production.sum()
        ) < 0.01

    def test_manual_profile_consumption_sum_matches(
        self,
        base_system_input: SystemInput,
        synthetic_production: ProductionData,
        config: dict[str, Any],
    ) -> None:
        from dataclasses import replace

        si_custom = replace(
            base_system_input,
            custom_hourly_kwh=tuple(EVENING_PEAK_24H),
        )

        result = compute_energy(si_custom, synthetic_production, config)
        assert abs(result.consumption.sum() - 4500.0) < 1.0

    @pytest.mark.skipif(
        not METER_DATA_DIR.is_dir(),
        reason="Meter data folder not available",
    )
    def test_meter_profile_overrides_default(
        self,
        base_system_input: SystemInput,
        synthetic_production: ProductionData,
        config: dict[str, Any],
    ) -> None:
        from dataclasses import replace

        si_meter = replace(
            base_system_input,
            custom_profile_dir="IT221E00549903",
        )

        result_default = compute_energy(base_system_input, synthetic_production, config)
        result_meter = compute_energy(si_meter, synthetic_production, config)

        # Should produce different autoconsumo
        assert result_default.tasso_autoconsumo != result_meter.tasso_autoconsumo

        # Energy balance
        assert abs(
            result_meter.autoconsumo.sum() + result_meter.immissione.sum()
            - result_meter.production.sum()
        ) < 0.01

    def test_manual_profile_priority_over_meter(
        self,
        base_system_input: SystemInput,
        synthetic_production: ProductionData,
        config: dict[str, Any],
    ) -> None:
        """custom_hourly_kwh should take priority over custom_profile_dir."""
        from dataclasses import replace

        si_both = replace(
            base_system_input,
            custom_hourly_kwh=tuple(FLAT_24H),
            custom_profile_dir="IT221E00549903",
        )
        si_manual = replace(
            base_system_input,
            custom_hourly_kwh=tuple(FLAT_24H),
        )

        result_both = compute_energy(si_both, synthetic_production, config)
        result_manual = compute_energy(si_manual, synthetic_production, config)

        # Should be identical — manual takes priority
        assert abs(result_both.tasso_autoconsumo - result_manual.tasso_autoconsumo) < 1e-10

    def test_custom_profile_with_heat_pump(
        self,
        base_system_input: SystemInput,
        synthetic_production: ProductionData,
        config: dict[str, Any],
    ) -> None:
        """Custom profile + heat pump should blend correctly."""
        from dataclasses import replace

        si_custom_hp = replace(
            base_system_input,
            custom_hourly_kwh=tuple(EVENING_PEAK_24H),
            heat_pump_kwh_annual=3500,
        )

        result = compute_energy(si_custom_hp, synthetic_production, config)

        # Total consumption should be base + HP
        expected_total = 4500 + 3500
        assert abs(result.consumption.sum() - expected_total) < 1.0

        # Energy balance
        assert abs(
            result.autoconsumo.sum() + result.immissione.sum()
            - result.production.sum()
        ) < 0.01
