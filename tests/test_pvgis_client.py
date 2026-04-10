"""Tests for PVGIS production data fetching."""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from celine.roi.models import SystemInput
from celine.roi.pvgis_client import fetch_production


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


_MOCK_PVGIS_MONTHLY = np.array(
    [2000, 2500, 3500, 4500, 5500, 6000, 6000, 5500, 4000, 3000, 2000, 1500], dtype=float
)
_MOCK_PVGIS_HOURLY = np.ones(8760, dtype=float) * (_MOCK_PVGIS_MONTHLY.sum() / 8760)
_MOCK_PVGIS = (_MOCK_PVGIS_MONTHLY, _MOCK_PVGIS_HOURLY)


class TestFetchProductionSynthetic:
    """Tests for manual override / synthetic fallback path."""

    async def test_returns_synthetic_source(self, input_with_override: SystemInput) -> None:
        result = await fetch_production(input_with_override)
        assert result.source == "synthetic"

    async def test_annual_matches_override(self, input_with_override: SystemInput) -> None:
        result = await fetch_production(input_with_override)
        assert result.annual_production_kwh == 49500.0

    async def test_monthly_sums_to_annual(self, input_with_override: SystemInput) -> None:
        result = await fetch_production(input_with_override)
        assert abs(result.monthly_production_kwh.sum() - 49500.0) < 0.01

    async def test_monthly_has_12_elements(self, input_with_override: SystemInput) -> None:
        result = await fetch_production(input_with_override)
        assert len(result.monthly_production_kwh) == 12

    async def test_summer_higher_than_winter(self, input_with_override: SystemInput) -> None:
        result = await fetch_production(input_with_override)
        monthly = result.monthly_production_kwh
        assert monthly[5] > monthly[11]  # June > December


class TestFetchProductionPVGIS:
    """Tests for PVGIS API path (mocked)."""

    async def test_pvgis_api_failure_falls_back_to_synthetic(
        self, input_without_override: SystemInput
    ) -> None:
        with patch(
            "celine.roi.pvgis_client._fetch_pvgis_monthly",
            new=AsyncMock(side_effect=ConnectionError("PVGIS unreachable")),
        ):
            result = await fetch_production(input_without_override)
        assert result.source == "synthetic"
        assert result.annual_production_kwh > 0
        assert len(result.hourly_production_kwh) == 8760

    async def test_pvgis_timeout_falls_back_to_synthetic(
        self, input_without_override: SystemInput
    ) -> None:
        with patch(
            "celine.roi.pvgis_client._fetch_pvgis_monthly",
            new=AsyncMock(side_effect=TimeoutError("PVGIS timed out")),
        ):
            result = await fetch_production(input_without_override)
        assert result.source == "synthetic"


_WKT_LAVARONE = (
    "POLYGON((11.266 45.933, 11.266 45.9332, 11.2664 45.9332, 11.2664 45.933, 11.266 45.933))"
)


class TestFetchProductionHybrid:
    """Tests for hybrid Trentino+PVGIS path."""

    async def test_hybrid_source_when_rooftop_wkt_provided(self) -> None:
        """Trentino LIDAR path triggers only when kwp=0 (auto-estimate mode)."""
        from celine.roi.trentino_solar import TrentinoSolarResult

        si = SystemInput(
            kwp=0, latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=0.0,
            capex=31400.0, annual_consumption_kwh=40000.0, user_type="commercial",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            rooftop_wkt=_WKT_LAVARONE,
        )

        mock_trentino = AsyncMock(return_value=TrentinoSolarResult(
            area=196.23, nominal_power_kwp=31.40,
            energy_yield_kwh_kwp=942.77, electrical_output_kwh=29599.37,
        ))
        mock_pvgis = AsyncMock(return_value=_MOCK_PVGIS)

        with (
            patch("celine.roi.pvgis_client.fetch_trentino_solar", mock_trentino),
            patch("celine.roi.pvgis_client._fetch_pvgis_monthly", mock_pvgis),
        ):
            result = await fetch_production(si)

        assert result.source == "trentino+pvgis"
        assert result.annual_production_kwh == pytest.approx(29599.37)
        assert len(result.monthly_production_kwh) == 12
        assert result.monthly_production_kwh.sum() == pytest.approx(29599.37, rel=1e-3)
        assert result.monthly_production_kwh[5] > result.monthly_production_kwh[11]

    async def test_fallback_to_pvgis_when_trentino_fails(self) -> None:
        si = SystemInput(
            kwp=0, latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=0.0,
            capex=31400.0, annual_consumption_kwh=40000.0, user_type="commercial",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            rooftop_wkt=_WKT_LAVARONE,
        )

        with (
            patch(
                "celine.roi.pvgis_client.fetch_trentino_solar",
                new=AsyncMock(side_effect=ConnectionError("API down")),
            ),
            patch("celine.roi.pvgis_client._fetch_pvgis_monthly", new=AsyncMock(return_value=_MOCK_PVGIS)),
        ):
            result = await fetch_production(si)

        assert result.source == "pvgis"

    async def test_no_hybrid_when_outside_trentino(self) -> None:
        si = SystemInput(
            kwp=45.0, latitude=41.9, longitude=12.5, tilt=30.0, azimuth=0.0,
            capex=45000.0, annual_consumption_kwh=40000.0, user_type="commercial",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            rooftop_wkt="POLYGON((12.5 41.9, 12.5 41.9002, 12.5004 41.9002, 12.5004 41.9, 12.5 41.9))",
        )

        with (
            patch("celine.roi.pvgis_client.fetch_trentino_solar") as mock_trentino,
            patch("celine.roi.pvgis_client._fetch_pvgis_monthly", new=AsyncMock(return_value=_MOCK_PVGIS)),
        ):
            result = await fetch_production(si)

        mock_trentino.assert_not_called()
        assert result.source == "pvgis"

    async def test_no_hybrid_when_kwp_specified_with_wkt(self) -> None:
        """When user specifies kWp (e.g. via panel count), skip LIDAR even with WKT in Trentino."""
        si = SystemInput(
            kwp=5.4, latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=0.0,
            capex=6600.0, annual_consumption_kwh=4000.0, user_type="residential",
            regime="RID", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            rooftop_wkt=_WKT_LAVARONE,
        )

        with (
            patch("celine.roi.pvgis_client.fetch_trentino_solar") as mock_trentino,
            patch("celine.roi.pvgis_client._fetch_pvgis_monthly", new=AsyncMock(return_value=_MOCK_PVGIS)),
        ):
            result = await fetch_production(si)

        mock_trentino.assert_not_called()
        assert result.source == "pvgis"
        assert result.effective_kwp is None

    async def test_no_hybrid_without_rooftop_wkt(self) -> None:
        si = SystemInput(
            kwp=45.0, latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=0.0,
            capex=45000.0, annual_consumption_kwh=40000.0, user_type="commercial",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
        )

        with patch("celine.roi.pvgis_client._fetch_pvgis_monthly", new=AsyncMock(return_value=_MOCK_PVGIS)):
            result = await fetch_production(si)

        assert result.source == "pvgis"
