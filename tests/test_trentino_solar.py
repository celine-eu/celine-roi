"""Tests for Trentino Solar Irradiance API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from celine.roi.trentino_solar import (
    TrentinoSolarResult,
    fetch_trentino_solar,
    is_in_trentino,
)

_WKT_LAVARONE = (
    "POLYGON((11.266 45.933, 11.266 45.9332, 11.2664 45.9332, 11.2664 45.933, 11.266 45.933))"
)
_WKT_MILANO = (
    "POLYGON((9.19 45.46, 9.19 45.4602, 9.1904 45.4602, 9.1904 45.46, 9.19 45.46))"
)


def _make_httpx_mock(json_payload: dict) -> tuple:
    """Return (mock_cls, mock_response) for patching httpx.AsyncClient."""
    mock_response = MagicMock()
    mock_response.json.return_value = json_payload
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_cls, mock_response


class TestIsInTrentino:
    """Bounding box check tests.

    @verifies REQ-0308
    """

    def test_lavarone_is_in_trentino(self) -> None:
        assert is_in_trentino(45.9333, 11.2667) is True

    def test_trento_is_in_trentino(self) -> None:
        assert is_in_trentino(46.0667, 11.1167) is True

    def test_milano_is_not_in_trentino(self) -> None:
        assert is_in_trentino(45.4642, 9.1900) is False

    def test_roma_is_not_in_trentino(self) -> None:
        assert is_in_trentino(41.9028, 12.4964) is False


class TestFetchTrentinoSolar:
    """Tests for async API client (httpx mocked).

    @verifies REQ-0308
    """

    async def test_successful_response(self) -> None:
        mock_cls, _ = _make_httpx_mock({
            "isValid": True,
            "area": 196.23,
            "nominalPower": 31.40,
            "energyYield": 942.77,
            "electricalOutput": 29599.37,
        })

        with patch("celine.roi.trentino_solar.httpx.AsyncClient", mock_cls):
            result = await fetch_trentino_solar(_WKT_LAVARONE)

        assert isinstance(result, TrentinoSolarResult)
        assert result.area == pytest.approx(196.23)
        assert result.nominal_power_kwp == pytest.approx(31.40)
        assert result.energy_yield_kwh_kwp == pytest.approx(942.77)
        assert result.electrical_output_kwh == pytest.approx(29599.37)

    async def test_outside_trentino_raises(self) -> None:
        mock_cls, _ = _make_httpx_mock({
            "isValid": False,
            "errorCode": "00008",
            "userMessage": "La geometria non ricade nell'ambito della Provincia Autonoma di Trento",
        })

        with patch("celine.roi.trentino_solar.httpx.AsyncClient", mock_cls):
            with pytest.raises(ValueError, match="non ricade"):
                await fetch_trentino_solar(_WKT_MILANO)

    @pytest.mark.parametrize(
        ("case", "payload"),
        [
            (
                "missing field",
                {"isValid": True, "nominalPower": 31.4, "energyYield": 942.77,
                 "electricalOutput": 29599.37},
            ),
            (
                "null field",
                {"isValid": True, "area": 196.23, "nominalPower": None,
                 "energyYield": 942.77, "electricalOutput": 29599.37},
            ),
            (
                "non-numeric field",
                {"isValid": True, "area": 196.23, "nominalPower": "n/a",
                 "energyYield": 942.77, "electricalOutput": 29599.37},
            ),
        ],
    )
    async def test_malformed_response_raises_value_error(self, case: str, payload: dict) -> None:
        """A response of the wrong shape is a bad response, and is reported as one.

        The exception type is the contract here, not an implementation detail: callers
        treat ValueError and ConnectionError as "Trentino is no use, fall back to PVGIS".
        A leaked KeyError or TypeError bypasses that and fails the whole request.
        """
        mock_cls, _ = _make_httpx_mock(payload)

        with patch("celine.roi.trentino_solar.httpx.AsyncClient", mock_cls):
            with pytest.raises(ValueError):
                await fetch_trentino_solar(_WKT_LAVARONE)

    async def test_connection_error_raises(self) -> None:
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Network error"))
        mock_cls = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("celine.roi.trentino_solar.httpx.AsyncClient", mock_cls):
            with pytest.raises(ConnectionError):
                await fetch_trentino_solar(_WKT_LAVARONE)
