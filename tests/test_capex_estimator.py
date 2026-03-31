"""Tests for the CAPEX estimator module."""

from __future__ import annotations

from pathlib import Path

import pytest

from celine.roi.capex_estimator import (
    estimate_capex,
    load_panel_specs,
    max_panels_for_area,
)

CONFIG_DIR = Path(__file__).parent.parent / "config"
SPECS_PATH = CONFIG_DIR / "panel_specs.yaml"


class TestLoadPanelSpecs:
    """Tests for loading panel specs config."""

    def test_loads_successfully(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        assert "panel" in specs
        assert "cost_curve" in specs
        assert "bounds" in specs

    def test_panel_specs_values(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        assert specs["panel"]["watt_peak"] == 450
        assert specs["panel"]["area_m2"] == pytest.approx(1.96)

    def test_cost_curve_values(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        assert specs["cost_curve"]["base_eur"] == 1500.0
        assert specs["cost_curve"]["exponent"] == 0.88


class TestMaxPanelsForArea:
    """Tests for computing max panels that fit on a rooftop."""

    def test_small_rooftop(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        # 10 m² → floor(10 / 1.96) = 5 panels
        assert max_panels_for_area(10.0, specs) == 5

    def test_medium_rooftop(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        # 50 m² → floor(50 / 1.96) = 25 panels
        assert max_panels_for_area(50.0, specs) == 25

    def test_large_rooftop(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        # 200 m² → floor(200 / 1.96) = 102 panels
        assert max_panels_for_area(200.0, specs) == 102

    def test_zero_area(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        assert max_panels_for_area(0.0, specs) == 0

    def test_max_capped_by_kwp_limit(self) -> None:
        """Enormous area should be capped by max_kwp config."""
        specs = load_panel_specs(SPECS_PATH)
        # 100,000 m² would fit 51,020 panels = 22,959 kWp
        # But max_kwp = 1000 → max panels = floor(1000 / 0.45) = 2222
        result = max_panels_for_area(100_000.0, specs)
        kwp = result * specs["panel"]["watt_peak"] / 1000
        assert kwp <= specs["bounds"]["max_kwp"]


class TestEstimateCapex:
    """Tests for CAPEX estimation from number of panels."""

    def test_returns_all_fields(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        result = estimate_capex(num_panels=10, rooftop_area_m2=50.0, specs=specs)
        assert "num_panels" in result
        assert "kwp" in result
        assert "capex_eur" in result
        assert "eur_per_kwp" in result
        assert "rooftop_area_m2" in result
        assert "max_panels" in result
        assert "rooftop_utilization_pct" in result

    def test_residential_6_panels(self) -> None:
        """6 panels = 2.7 kWp → expect ~3,700 EUR (~1,370 EUR/kWp)."""
        specs = load_panel_specs(SPECS_PATH)
        result = estimate_capex(num_panels=6, rooftop_area_m2=50.0, specs=specs)
        assert result["kwp"] == pytest.approx(2.7)
        assert 3_000 < result["capex_eur"] < 5_000
        assert 1_100 < result["eur_per_kwp"] < 1_500

    def test_small_commercial_30_panels(self) -> None:
        """30 panels = 13.5 kWp → expect ~14,500 EUR (~1,075 EUR/kWp)."""
        specs = load_panel_specs(SPECS_PATH)
        result = estimate_capex(num_panels=30, rooftop_area_m2=100.0, specs=specs)
        assert result["kwp"] == pytest.approx(13.5)
        assert 12_000 < result["capex_eur"] < 18_000
        assert 900 < result["eur_per_kwp"] < 1_200

    def test_medium_commercial_100_panels(self) -> None:
        """100 panels = 45 kWp → expect ~42,000 EUR (~930 EUR/kWp)."""
        specs = load_panel_specs(SPECS_PATH)
        result = estimate_capex(num_panels=100, rooftop_area_m2=300.0, specs=specs)
        assert result["kwp"] == pytest.approx(45.0)
        assert 35_000 < result["capex_eur"] < 50_000
        assert 800 < result["eur_per_kwp"] < 1_050

    def test_economies_of_scale(self) -> None:
        """Larger systems should have lower EUR/kWp."""
        specs = load_panel_specs(SPECS_PATH)
        small = estimate_capex(num_panels=8, rooftop_area_m2=50.0, specs=specs)
        large = estimate_capex(num_panels=100, rooftop_area_m2=300.0, specs=specs)
        assert large["eur_per_kwp"] < small["eur_per_kwp"]

    def test_too_few_panels_raises(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        with pytest.raises(ValueError, match="minimum"):
            estimate_capex(num_panels=2, rooftop_area_m2=50.0, specs=specs)

    def test_too_many_panels_raises(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        # 50 m² fits 25 panels max
        with pytest.raises(ValueError, match="maximum"):
            estimate_capex(num_panels=30, rooftop_area_m2=50.0, specs=specs)

    def test_rooftop_utilization(self) -> None:
        specs = load_panel_specs(SPECS_PATH)
        result = estimate_capex(num_panels=10, rooftop_area_m2=50.0, specs=specs)
        # 10 panels * 1.96 m² = 19.6 m² → 39.2% utilization
        assert result["rooftop_utilization_pct"] == pytest.approx(39.2, abs=0.5)

    def test_floor_cost_applied(self) -> None:
        """Minimum panels should still cost at least floor_eur."""
        specs = load_panel_specs(SPECS_PATH)
        result = estimate_capex(num_panels=4, rooftop_area_m2=50.0, specs=specs)
        assert result["capex_eur"] >= specs["cost_curve"]["floor_eur"]
