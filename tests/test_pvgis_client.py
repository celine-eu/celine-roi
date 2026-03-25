"""Tests for PVGIS production data fetching."""

from unittest.mock import patch

import pytest

from celine_roi.models import SystemInput
from celine_roi.pvgis_client import fetch_production


@pytest.fixture()
def input_with_override() -> SystemInput:
    """SystemInput with manual production override (skips PVGIS)."""
    return SystemInput(
        kwp=45.0, latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=0.0,
        capex=45000.0, annual_consumption_kwh=40000.0, user_type="commercial",
        regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
        annual_production_kwh=49500.0,
    )


@pytest.fixture()
def input_without_override() -> SystemInput:
    """SystemInput without override (requires PVGIS)."""
    return SystemInput(
        kwp=45.0, latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=0.0,
        capex=45000.0, annual_consumption_kwh=40000.0, user_type="commercial",
        regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
    )


class TestFetchProductionSynthetic:
    """Tests for manual override / synthetic fallback path."""

    def test_returns_synthetic_source(self, input_with_override: SystemInput) -> None:
        result = fetch_production(input_with_override)
        assert result.source == "synthetic"

    def test_annual_matches_override(self, input_with_override: SystemInput) -> None:
        result = fetch_production(input_with_override)
        assert result.annual_production_kwh == 49500.0

    def test_monthly_sums_to_annual(self, input_with_override: SystemInput) -> None:
        result = fetch_production(input_with_override)
        assert abs(result.monthly_production_kwh.sum() - 49500.0) < 0.01

    def test_monthly_has_12_elements(self, input_with_override: SystemInput) -> None:
        result = fetch_production(input_with_override)
        assert len(result.monthly_production_kwh) == 12

    def test_summer_higher_than_winter(self, input_with_override: SystemInput) -> None:
        result = fetch_production(input_with_override)
        monthly = result.monthly_production_kwh
        assert monthly[5] > monthly[11]  # June > December


class TestFetchProductionPVGIS:
    """Tests for PVGIS API path (mocked)."""

    def test_pvgis_api_failure_raises_error(
        self, input_without_override: SystemInput
    ) -> None:
        with patch(
            "celine_roi.pvgis_client._fetch_pvgis_monthly",
            side_effect=ConnectionError("PVGIS unreachable")
        ):
            with pytest.raises(ConnectionError, match="PVGIS unreachable"):
                fetch_production(input_without_override)

    def test_does_not_silently_fallback(
        self, input_without_override: SystemInput
    ) -> None:
        with patch(
            "celine_roi.pvgis_client._fetch_pvgis_monthly",
            side_effect=ConnectionError("fail")
        ):
            with pytest.raises(ConnectionError):
                fetch_production(input_without_override)
