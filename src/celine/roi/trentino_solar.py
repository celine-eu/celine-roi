"""Trentino Solar Irradiance API client.

Queries the Provincia Autonoma di Trento WebGIS service for LIDAR-based
solar irradiance statistics on rooftop polygons. More accurate than PVGIS
for mountain terrain due to shadow-corrected DSM.

Results are cached by WKT geometry hash — LIDAR data is static for a given
polygon. Cache is in-memory by default; set TRENTINO_SOLAR_CACHE_DIR to
persist to disk across runs.

Coverage: Trentino only. Returns error for locations outside PAT boundaries.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

TRENTINO_SOLAR_URL = "https://webgis.provincia.tn.it/wgt/services/solarIrradiance/statistics"

_cache: dict[str, TrentinoSolarResult] = {}


def _cache_dir() -> Path | None:
    d = os.environ.get("TRENTINO_SOLAR_CACHE_DIR")
    if d:
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return None


def _cache_key(rooftop_wkt: str, epsg_code: str) -> str:
    return hashlib.sha256(f"{epsg_code}:{rooftop_wkt}".encode()).hexdigest()


def _read_disk_cache(key: str) -> TrentinoSolarResult | None:
    d = _cache_dir()
    if d is None:
        return None
    path = d / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return TrentinoSolarResult(**data)
    except (json.JSONDecodeError, KeyError, TypeError):
        path.unlink(missing_ok=True)
        return None


def _write_disk_cache(key: str, result: TrentinoSolarResult) -> None:
    d = _cache_dir()
    if d is None:
        return
    path = d / f"{key}.json"
    path.write_text(json.dumps(asdict(result)))


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

    Results are cached by WKT hash. Set TRENTINO_SOLAR_CACHE_DIR env var
    to persist the cache to disk across process restarts.

    Args:
        rooftop_wkt: WKT polygon geometry of the rooftop.
        epsg_code: Coordinate reference system ("4326" for lat/lon, "25832" for UTM).

    Returns:
        TrentinoSolarResult with area, power, yield, and production.

    Raises:
        ValueError: If the geometry is outside Trentino or invalid.
        ConnectionError: If the API is unreachable.
    """
    key = _cache_key(rooftop_wkt, epsg_code)

    if key in _cache:
        logger.debug("Trentino Solar cache hit (memory): %s…", key[:12])
        return _cache[key]

    disk_result = _read_disk_cache(key)
    if disk_result is not None:
        _cache[key] = disk_result
        logger.debug("Trentino Solar cache hit (disk): %s…", key[:12])
        return disk_result

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

    _cache[key] = result
    _write_disk_cache(key, result)

    logger.info(
        "Trentino Solar: area=%.1f m², kWp=%.1f, yield=%.0f kWh/kWp, output=%.0f kWh",
        result.area,
        result.nominal_power_kwp,
        result.energy_yield_kwh_kwp,
        result.electrical_output_kwh,
    )

    return result


def clear_cache() -> None:
    """Clear the in-memory cache. Disk cache is not affected."""
    _cache.clear()


def is_in_trentino(latitude: float, longitude: float) -> bool:
    """Quick bounding box check for Trentino province.

    Args:
        latitude: Site latitude.
        longitude: Site longitude.

    Returns:
        True if coordinates fall within Trentino's approximate bounding box.
    """
    return 45.67 <= latitude <= 47.09 and 10.38 <= longitude <= 11.84
