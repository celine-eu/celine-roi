"""Trentino Solar Irradiance API client.

Queries the Provincia Autonoma di Trento WebGIS service for LIDAR-based
solar irradiance statistics on rooftop polygons. More accurate than PVGIS
for mountain terrain due to shadow-corrected DSM.

Coverage: Trentino only. Returns error for locations outside PAT boundaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

TRENTINO_SOLAR_URL = "https://webgis.provincia.tn.it/wgt/services/solarIrradiance/statistics"


@dataclass(frozen=True)
class TrentinoSolarResult:
    """Result from Trentino Solar Irradiance API.

    Args:
        area: Usable rooftop area in m².
        nominal_power_kwp: Maximum installable capacity in kWp (at ~160 W/m²).
        energy_yield_kwh_kwp: Specific yield in kWh/kWp (shadow-corrected).
        electrical_output_kwh: Expected annual production in kWh.
    """

    area: float
    nominal_power_kwp: float
    energy_yield_kwh_kwp: float
    electrical_output_kwh: float


async def fetch_trentino_solar(
    rooftop_wkt: str,
    epsg_code: str = "4326",
) -> TrentinoSolarResult:
    """Query Trentino Solar Irradiance API for a rooftop polygon.

    Args:
        rooftop_wkt: WKT polygon geometry of the rooftop.
        epsg_code: Coordinate reference system ("4326" for lat/lon, "25832" for UTM).

    Returns:
        TrentinoSolarResult with area, power, yield, and production.

    Raises:
        ValueError: If the geometry is outside Trentino or invalid.
        ConnectionError: If the API is unreachable.
    """
    logger.info("Querying Trentino Solar API (EPSG:%s)", epsg_code)

    payload = {
        "epsgCode": epsg_code,
        "wktGeometry": rooftop_wkt,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                TRENTINO_SOLAR_URL,
                json=payload,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError as exc:
        raise ConnectionError(f"Trentino Solar API unreachable: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise ConnectionError(
            f"Trentino Solar API error: {exc.response.status_code}"
        ) from exc

    if not data.get("isValid", False):
        error_msg = data.get("userMessage", "Unknown error")
        error_code = data.get("errorCode", "")
        raise ValueError(f"Trentino Solar API: {error_msg} (code: {error_code})")

    result = TrentinoSolarResult(
        area=data["area"],
        nominal_power_kwp=data["nominalPower"],
        energy_yield_kwh_kwp=data["energyYield"],
        electrical_output_kwh=data["electricalOutput"],
    )

    logger.info(
        "Trentino Solar: area=%.1f m², kWp=%.1f, yield=%.0f kWh/kWp, output=%.0f kWh",
        result.area,
        result.nominal_power_kwp,
        result.energy_yield_kwh_kwp,
        result.electrical_output_kwh,
    )

    return result


def is_in_trentino(latitude: float, longitude: float) -> bool:
    """Quick bounding box check for Trentino province.

    Args:
        latitude: Site latitude.
        longitude: Site longitude.

    Returns:
        True if coordinates fall within Trentino's approximate bounding box.
    """
    return 45.67 <= latitude <= 47.09 and 10.38 <= longitude <= 11.84
