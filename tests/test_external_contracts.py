"""Contract tests for the two external services this repository calls.

`pvgis_client.py` is the only module that reaches the network, and both services it
talks to are mocked everywhere else in the suite. What the existing mocks assert is the
*inbound* half — that a well-formed response is parsed correctly. This file covers the
parts a mock cannot notice going wrong:

- the request this repository sends, whose field names are as much of a contract as the
  response's;
- the two coordinate conventions it converts between, both of which are silent when
  reversed — a sign error in azimuth returns a plausible number for the wrong roof;
- what happens when an upstream response is shaped differently than expected.

None of this can detect a real upstream change on its own. It can detect *this* side
drifting away from what was recorded, which is the half that is in this repository's
control.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from celine.roi.models import SystemInput
from celine.roi.pvgis_client import (
    _fetch_pvgis_monthly_blocking,
    detect_epsg,
    fetch_production,
)
from celine.roi.trentino_solar import TRENTINO_SOLAR_URL, fetch_trentino_solar

_WKT_LAVARONE = (
    "POLYGON((11.266 45.933, 11.266 45.9332, 11.2664 45.9332, 11.2664 45.933, 11.266 45.933))"
)

_MOCK_PVGIS_MONTHLY = np.array(
    [2000, 2500, 3500, 4500, 5500, 6000, 6000, 5500, 4000, 3000, 2000, 1500], dtype=float
)
_MOCK_PVGIS = (_MOCK_PVGIS_MONTHLY, np.ones(8760) * (_MOCK_PVGIS_MONTHLY.sum() / 8760))

# A response with every documented field, as the service returns them.
_VALID_TRENTINO_PAYLOAD = {
    "isValid": True,
    "area": 196.23,
    "nominalPower": 31.40,
    "energyYield": 942.77,
    "electricalOutput": 29599.37,
}


def _httpx_mock(json_payload: dict) -> tuple:
    response = MagicMock()
    response.json.return_value = json_payload
    response.raise_for_status = MagicMock()

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return cls, client


# @verifies REQ-0301
class TestTrentinoRequestContract:

    async def test_request_shape(self) -> None:
        """The outbound field names are a contract too, and no other test reads them."""
        cls, client = _httpx_mock(_VALID_TRENTINO_PAYLOAD)

        with patch("celine.roi.trentino_solar.httpx.AsyncClient", cls):
            await fetch_trentino_solar(_WKT_LAVARONE, epsg_code="25832")

        client.post.assert_called_once()
        url = client.post.call_args.args[0]
        payload = client.post.call_args.kwargs["json"]

        assert url == TRENTINO_SOLAR_URL
        assert payload == {"epsgCode": "25832", "wktGeometry": _WKT_LAVARONE}


# @verifies REQ-0302
class TestDetectEpsg:

    def test_latlon_polygon_is_4326(self) -> None:
        assert detect_epsg(_WKT_LAVARONE) == "4326"

    def test_utm_polygon_is_25832(self) -> None:
        utm = "POLYGON((664000 5090000, 664000 5090020, 664020 5090020, 664000 5090000))"
        assert detect_epsg(utm) == "25832"

    def test_empty_geometry_defaults_to_latlon(self) -> None:
        assert detect_epsg("POLYGON(())") == "4326"

    def test_negative_longitude_is_still_latlon(self) -> None:
        """Coordinate magnitude decides, not sign — a western site must not read as UTM."""
        western = "POLYGON((-9.14 38.72, -9.14 38.7202, -9.1396 38.7202, -9.14 38.72))"
        assert detect_epsg(western) == "4326"


# @verifies REQ-0303
class TestPvgisAzimuthConvention:

    @staticmethod
    def _capture_pvgis_call(azimuth: float) -> dict:
        """Run the blocking fetch against a stub and return the kwargs pvlib received."""
        index = pd.date_range("2020-01-01", periods=8760, freq="h", tz="UTC")
        frame = pd.DataFrame({"P": np.ones(8760) * 1000.0}, index=index)

        with patch("pvlib.iotools.get_pvgis_hourly", return_value=(frame, {}, {})) as stub:
            _fetch_pvgis_monthly_blocking(
                latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=azimuth, kwp=10.0
            )
        return stub.call_args.kwargs

    def test_south_facing_becomes_pvlib_180(self) -> None:
        """SystemInput uses PVGIS convention (0=south); pvlib uses 0=north.

        Getting this backwards is silent: the call succeeds and returns the yield of a
        north-facing roof.
        """
        assert self._capture_pvgis_call(0.0)["surface_azimuth"] == pytest.approx(180.0)

    def test_west_facing_becomes_pvlib_270(self) -> None:
        assert self._capture_pvgis_call(90.0)["surface_azimuth"] == pytest.approx(270.0)

    def test_east_facing_becomes_pvlib_90(self) -> None:
        assert self._capture_pvgis_call(-90.0)["surface_azimuth"] == pytest.approx(90.0)

    def test_tilt_and_capacity_pass_through_unchanged(self) -> None:
        kwargs = self._capture_pvgis_call(0.0)
        assert kwargs["surface_tilt"] == pytest.approx(30.0)
        assert kwargs["peakpower"] == pytest.approx(10.0)
        assert kwargs["pvcalculation"] is True


# @verifies REQ-0304
class TestPvgisSeriesAreConsistent:

    @staticmethod
    def _fetch_with_rows(n_rows: int) -> tuple[np.ndarray, np.ndarray]:
        index = pd.date_range("2020-01-01", periods=n_rows, freq="h", tz="UTC")
        frame = pd.DataFrame({"P": np.ones(n_rows) * 1000.0}, index=index)
        with patch("pvlib.iotools.get_pvgis_hourly", return_value=(frame, {}, {})):
            return _fetch_pvgis_monthly_blocking(
                latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=0.0, kwp=10.0
            )

    def test_hourly_is_always_8760(self) -> None:
        """A leap-year TMY returns 8784 rows. Both series must still line up."""
        _, hourly = self._fetch_with_rows(8784)
        assert len(hourly) == 8760

    def test_short_series_is_padded_to_8760(self) -> None:
        _, hourly = self._fetch_with_rows(8000)
        assert len(hourly) == 8760
        assert hourly[8000:].sum() == pytest.approx(0.0)

    def test_monthly_has_twelve_entries(self) -> None:
        monthly, _ = self._fetch_with_rows(8760)
        assert len(monthly) == 12

    def test_watts_are_converted_to_kwh(self) -> None:
        """P is in Watts and each row is one hour, so 1000 W ⇒ 1 kWh."""
        _, hourly = self._fetch_with_rows(8760)
        assert hourly[0] == pytest.approx(1.0)


# @verifies REQ-0305
class TestTrentinoFailureIsVisibleToTheCaller:

    async def test_fallback_is_reported_in_source(self) -> None:
        """The fallback is quiet in the logs but not in the payload.

        When Trentino fails the client logs a warning and returns PVGIS numbers. The
        only thing that distinguishes the two outcomes for a caller is `source`, so a
        change that stopped setting it would make a broken integration look like a
        working service returning a slightly different answer.
        """
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
            patch(
                "celine.roi.pvgis_client._fetch_pvgis_monthly",
                new=AsyncMock(return_value=_MOCK_PVGIS),
            ),
        ):
            result = await fetch_production(si)

        assert result.source == "pvgis"
        assert result.effective_kwp is None

    @pytest.mark.parametrize(
        ("description", "mutate"),
        [
            (
                "renamed field",
                lambda p: {
                    ("nominalPowerKwp" if k == "nominalPower" else k): v
                    for k, v in p.items()
                },
            ),
            ("dropped field", lambda p: {k: v for k, v in p.items() if k != "area"}),
            ("null where a number belongs", lambda p: {**p, "energyYield": None}),
            ("string where a number belongs", lambda p: {**p, "electricalOutput": "n/a"}),
        ],
    )
    async def test_malformed_trentino_response_falls_back(
        self, description: str, mutate
    ) -> None:
        """An upstream shape change degrades to PVGIS rather than failing the request.

        This is the point of the fallback. Until 2026-08-15 it did not hold: the client
        indexed the response dict directly, so a renamed field raised `KeyError`, which
        `fetch_production`'s `except (ValueError, ConnectionError)` does not catch — and
        a Trentino shape change took out every scenario request for a Trentino rooftop.
        """
        si = SystemInput(
            kwp=0, latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=0.0,
            capex=31400.0, annual_consumption_kwh=40000.0, user_type="commercial",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            rooftop_wkt=_WKT_LAVARONE,
        )
        cls, _ = _httpx_mock(mutate(dict(_VALID_TRENTINO_PAYLOAD)))

        with (
            patch("celine.roi.trentino_solar.httpx.AsyncClient", cls),
            patch(
                "celine.roi.pvgis_client._fetch_pvgis_monthly",
                new=AsyncMock(return_value=_MOCK_PVGIS),
            ),
        ):
            result = await fetch_production(si)

        assert result.source == "pvgis", f"did not fall back on a {description}"
