"""Tests for Trentino Solar Irradiance API client."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from celine_roi.trentino_solar import (
    TrentinoSolarResult,
    fetch_trentino_solar,
    is_in_trentino,
)


class TestIsInTrentino:
    """Bounding box check tests."""

    def test_lavarone_is_in_trentino(self) -> None:
        assert is_in_trentino(45.9333, 11.2667) is True

    def test_trento_is_in_trentino(self) -> None:
        assert is_in_trentino(46.0667, 11.1167) is True

    def test_milano_is_not_in_trentino(self) -> None:
        assert is_in_trentino(45.4642, 9.1900) is False

    def test_roma_is_not_in_trentino(self) -> None:
        assert is_in_trentino(41.9028, 12.4964) is False


_WKT_LAVARONE = (
    "POLYGON((11.266 45.933, 11.266 45.9332, 11.2664 45.9332, 11.2664 45.933, 11.266 45.933))"
)
_WKT_MILANO = (
    "POLYGON((9.19 45.46, 9.19 45.4602, 9.1904 45.4602, 9.1904 45.46, 9.19 45.46))"
)


class TestFetchTrentinoSolar:
    """Tests for API client (mocked)."""

    def test_successful_response(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "isValid": True,
            "area": 196.23,
            "nominalPower": 31.40,
            "energyYield": 942.77,
            "electricalOutput": 29599.37,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("celine_roi.trentino_solar.requests.post", return_value=mock_response):
            result = fetch_trentino_solar(_WKT_LAVARONE)

        assert isinstance(result, TrentinoSolarResult)
        assert result.area == pytest.approx(196.23)
        assert result.nominal_power_kwp == pytest.approx(31.40)
        assert result.energy_yield_kwh_kwp == pytest.approx(942.77)
        assert result.electrical_output_kwh == pytest.approx(29599.37)

    def test_outside_trentino_raises(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "isValid": False,
            "errorCode": "00008",
            "userMessage": "La geometria non ricade nell'ambito della Provincia Autonoma di Trento",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("celine_roi.trentino_solar.requests.post", return_value=mock_response):
            with pytest.raises(ValueError, match="non ricade"):
                fetch_trentino_solar(_WKT_MILANO)

    def test_connection_error_raises(self) -> None:
        with patch(
            "celine_roi.trentino_solar.requests.post",
            side_effect=Exception("Network error"),
        ):
            with pytest.raises(Exception):
                fetch_trentino_solar(_WKT_LAVARONE)


class TestFetchProductionHybrid:
    """Tests for hybrid Trentino+PVGIS path in fetch_production."""

    def test_hybrid_source_when_rooftop_wkt_provided(self, config) -> None:
        """When rooftop_wkt is set and in Trentino, source should be trentino+pvgis."""
        from celine_roi.models import SystemInput
        from celine_roi.pvgis_client import fetch_production

        si = SystemInput(
            kwp=31.4,
            latitude=45.9333,
            longitude=11.2667,
            tilt=30.0,
            azimuth=0.0,
            capex=31400.0,
            annual_consumption_kwh=40000.0,
            user_type="commercial",
            regime="RID_CER",
            equity_fraction=1.0,
            loan_rate=0.0,
            loan_duration_years=0,
            rooftop_wkt=_WKT_LAVARONE,
        )

        mock_trentino = MagicMock()
        mock_trentino.return_value = TrentinoSolarResult(
            area=196.23,
            nominal_power_kwp=31.40,
            energy_yield_kwh_kwp=942.77,
            electrical_output_kwh=29599.37,
        )

        mock_pvgis = MagicMock()
        mock_pvgis.return_value = np.array(
            [2000, 2500, 3500, 4500, 5500, 6000, 6000, 5500, 4000, 3000, 2000, 1500],
            dtype=float,
        )  # 46,000 kWh total from PVGIS

        with (
            patch("celine_roi.pvgis_client.fetch_trentino_solar", mock_trentino),
            patch("celine_roi.pvgis_client._fetch_pvgis_monthly", mock_pvgis),
        ):
            result = fetch_production(si)

        assert result.source == "trentino+pvgis"
        assert result.annual_production_kwh == pytest.approx(29599.37)
        assert len(result.monthly_production_kwh) == 12
        # Monthly should sum to Trentino annual
        assert result.monthly_production_kwh.sum() == pytest.approx(29599.37, rel=1e-3)
        # Monthly shape should follow PVGIS pattern (June > December)
        assert result.monthly_production_kwh[5] > result.monthly_production_kwh[11]

    def test_fallback_to_pvgis_when_trentino_fails(self, config) -> None:
        """If Trentino API fails, should fall back to PVGIS only."""
        from celine_roi.models import SystemInput
        from celine_roi.pvgis_client import fetch_production

        si = SystemInput(
            kwp=31.4,
            latitude=45.9333,
            longitude=11.2667,
            tilt=30.0,
            azimuth=0.0,
            capex=31400.0,
            annual_consumption_kwh=40000.0,
            user_type="commercial",
            regime="RID_CER",
            equity_fraction=1.0,
            loan_rate=0.0,
            loan_duration_years=0,
            rooftop_wkt=_WKT_LAVARONE,
        )

        mock_pvgis = MagicMock()
        mock_pvgis.return_value = np.array(
            [2000, 2500, 3500, 4500, 5500, 6000, 6000, 5500, 4000, 3000, 2000, 1500],
            dtype=float,
        )

        with (
            patch(
                "celine_roi.pvgis_client.fetch_trentino_solar",
                side_effect=ConnectionError("API down"),
            ),
            patch("celine_roi.pvgis_client._fetch_pvgis_monthly", mock_pvgis),
        ):
            result = fetch_production(si)

        assert result.source == "pvgis"

    def test_no_hybrid_when_outside_trentino(self, config) -> None:
        """If coordinates outside Trentino, should not call Trentino API."""
        from celine_roi.models import SystemInput
        from celine_roi.pvgis_client import fetch_production

        si = SystemInput(
            kwp=45.0,
            latitude=41.9,  # Roma
            longitude=12.5,
            tilt=30.0,
            azimuth=0.0,
            capex=45000.0,
            annual_consumption_kwh=40000.0,
            user_type="commercial",
            regime="RID_CER",
            equity_fraction=1.0,
            loan_rate=0.0,
            loan_duration_years=0,
            rooftop_wkt=(
                "POLYGON((12.5 41.9, 12.5 41.9002, 12.5004 41.9002, 12.5004 41.9, 12.5 41.9))"
            ),
        )

        mock_pvgis = MagicMock()
        mock_pvgis.return_value = np.array(
            [3000, 3500, 4500, 5500, 6500, 7000, 7000, 6500, 5000, 4000, 3000, 2500],
            dtype=float,
        )

        with (
            patch("celine_roi.pvgis_client.fetch_trentino_solar") as mock_trentino,
            patch("celine_roi.pvgis_client._fetch_pvgis_monthly", mock_pvgis),
        ):
            result = fetch_production(si)

        mock_trentino.assert_not_called()
        assert result.source == "pvgis"

    def test_no_hybrid_without_rooftop_wkt(self, config) -> None:
        """Without rooftop_wkt, should use PVGIS only."""
        from celine_roi.models import SystemInput
        from celine_roi.pvgis_client import fetch_production

        si = SystemInput(
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
        )

        mock_pvgis = MagicMock()
        mock_pvgis.return_value = np.array(
            [2000, 2500, 3500, 4500, 5500, 6000, 6000, 5500, 4000, 3000, 2000, 1500],
            dtype=float,
        )

        with patch("celine_roi.pvgis_client._fetch_pvgis_monthly", mock_pvgis):
            result = fetch_production(si)

        assert result.source == "pvgis"
