"""Tests for custom personal consumption profiles.

Covers:
- Manual 24h kWh input (profile_from_manual_hourly)
- Meter data folder loading (load_meter_data_profile)
- Energy engine integration (custom profiles override user_type default)
- Full pipeline with custom profiles
"""

from __future__ import annotations

import json
import shutil
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


# ── Fixtures ──────────────────────────────────────────────────────────────────


# One day of half-plausible residential draw, in kWh per hour. The shape only has to be
# uneven enough that the coefficients it produces are distinguishable from a flat one.
_METER_DAY_KWH = [
    0.18, 0.15, 0.12, 0.11, 0.11, 0.13,
    0.20, 0.28, 0.30, 0.26, 0.22, 0.24,
    0.30, 0.28, 0.24, 0.22, 0.26, 0.38,
    0.55, 0.72, 0.68, 0.50, 0.34, 0.22,
]


METER_FOLDER_NAME = "meter-test-profile"


def _write_meter_days(folder: Path) -> None:
    """Write two months of daily meter exports into `folder`.

    February is given a colder, higher draw than July so that the monthly weighting has
    something to distinguish.
    """
    for month, days, scale in ((2, 8, 1.35), (7, 6, 0.80)):
        for day in range(1, days + 1):
            payload = {
                "imported": {
                    "data": {
                        "consumptions": [
                            {"month": month, "hour": hour, "total": round(kwh * scale, 4)}
                            for hour, kwh in enumerate(_METER_DAY_KWH)
                        ]
                    }
                }
            }
            (folder / f"2026-{month:02d}-{day:02d}.json").write_text(json.dumps(payload))


@pytest.fixture()
def meter_config_dir(tmp_path: Path) -> Path:
    """A config directory laid out as the engine expects, holding one meter profile.

    The repository's real load profiles are mirrored alongside it, so a test that patches
    `_CONFIG_DIR` at this directory can still resolve the by-user-type defaults it is
    comparing the meter profile against.
    """
    profiles = tmp_path / "config" / "load_profiles"
    folder = profiles / METER_FOLDER_NAME
    folder.mkdir(parents=True)
    _write_meter_days(folder)

    for real in LOAD_PROFILES_DIR.glob("*.json"):
        shutil.copy(real, profiles / real.name)

    return tmp_path / "config"


@pytest.fixture()
def meter_data_dir(meter_config_dir: Path) -> Path:
    """A folder of daily smart-meter files in the C2G / e-distribuzione format.

    These tests used to point at `config/load_profiles/<POD>`, a folder of one
    customer's real meter readings that exists on one machine and is gitignored. The
    consequence was that every test needing it skipped everywhere — the loader had no
    running coverage at all, and the skip reason ("Meter data folder not available")
    read like an environment quirk rather than missing verification.

    Synthesising the folder instead costs the one thing real data gave — proof that the
    upstream export still has this shape — which the tests never checked anyway, since
    nowhere that runs them had the folder. What is gained is that the loader's own
    contract is now verified: the file naming, the nesting, the per-month accumulation
    and the normalisation.
    """
    return meter_config_dir / "load_profiles" / METER_FOLDER_NAME


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
    """Tests for profile_from_manual_hourly().

    @verifies REQ-0804
    """

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
    """Tests for load_meter_data_profile().

    @verifies REQ-0804
    """

    def test_loads_meter_data(self, meter_data_dir: Path) -> None:
        profile = load_meter_data_profile(meter_data_dir)
        assert len(profile["hourly_coefficients"]) == 24
        assert len(profile["monthly_weights"]) == 12
        assert abs(sum(profile["hourly_coefficients"]) - 1.0) < 0.01
        assert abs(sum(profile["monthly_weights"]) - 1.0) < 0.01

    def test_daily_avg_positive(self, meter_data_dir: Path) -> None:
        profile = load_meter_data_profile(meter_data_dir)
        assert profile["daily_avg_kwh"] > 0

    def test_months_covered(self, meter_data_dir: Path) -> None:
        profile = load_meter_data_profile(meter_data_dir)
        assert set(profile["months_covered"]) == {2, 7}

    def test_hourly_shape_follows_the_readings(self, meter_data_dir: Path) -> None:
        """The evening peak in the readings must survive into the coefficients."""
        profile = load_meter_data_profile(meter_data_dir)
        coeffs = profile["hourly_coefficients"]
        assert coeffs[19] == pytest.approx(max(coeffs))
        assert coeffs[19] > coeffs[3] * 3

    def test_month_with_more_draw_gets_more_weight(self, meter_data_dir: Path) -> None:
        """February is written with a higher daily draw than July, and must weigh more."""
        profile = load_meter_data_profile(meter_data_dir)
        weights = profile["monthly_weights"]
        assert weights[1] > weights[6]

    def test_build_consumption_from_meter_profile(self, meter_data_dir: Path) -> None:
        profile = load_meter_data_profile(meter_data_dir)
        consumption = build_hourly_consumption(3500.0, profile)
        assert len(consumption) == 8760
        assert abs(consumption.sum() - 3500.0) < 0.1

    def test_invalid_files_are_skipped_not_fatal(self, meter_data_dir: Path) -> None:
        """One unreadable export must not lose the rest of the folder."""
        (meter_data_dir / "2026-02-99.json").write_text("{not json")
        (meter_data_dir / "2026-02-98.json").write_text('{"imported": {}}')

        profile = load_meter_data_profile(meter_data_dir)
        assert len(profile["hourly_coefficients"]) == 24

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
    """Test that custom profiles are used by the energy engine.

    @verifies REQ-0804
    """

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

    def test_meter_profile_overrides_default(
        self,
        base_system_input: SystemInput,
        synthetic_production: ProductionData,
        config: dict[str, Any],
        meter_config_dir: Path,
        monkeypatch,
    ) -> None:
        from dataclasses import replace

        import celine.roi.engines.energy as energy_mod

        # `_CONFIG_DIR` is read from CELINE_CONFIG_DIR at import, so the env var is
        # already too late by the time a test runs — the attribute has to be set.
        # Same trap as the settings singleton; see
        # .agents/knowledge/settings-are-read-once-at-import.md.
        monkeypatch.setattr(energy_mod, "_CONFIG_DIR", meter_config_dir)

        si_meter = replace(
            base_system_input,
            custom_profile_dir=METER_FOLDER_NAME,
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
            custom_profile_dir=METER_FOLDER_NAME,
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
