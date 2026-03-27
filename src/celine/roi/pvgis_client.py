"""PVGIS production data client.

Primary path: fetches real monthly production via pvlib's PVGIS integration.
Fallback path: distributes a user-provided annual total using a synthetic
solar curve (Trentino 46N latitude approximation).

pvlib has no async interface; the blocking HTTP call is offloaded to the
default thread pool executor via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from celine.roi.models import ProductionData, SystemInput
from celine.roi.trentino_solar import fetch_trentino_solar, is_in_trentino

logger = logging.getLogger(__name__)

# Normalized solar distribution for Trentino (46N latitude)
_RAW_SOLAR = [0.049, 0.059, 0.078, 0.098, 0.118, 0.127, 0.127, 0.118, 0.088, 0.069, 0.039, 0.029]
SOLAR_MONTHLY_FRACTIONS: np.ndarray = np.array(_RAW_SOLAR) / sum(_RAW_SOLAR)


def detect_epsg(wkt: str) -> str:
    """Detect EPSG code from WKT coordinate magnitudes.

    EPSG:4326 (lat/lon) has coordinates < 180.
    EPSG:25832 (UTM zone 32N) has coordinates in the 100,000s-5,000,000s range.

    Args:
        wkt: WKT geometry string.

    Returns:
        "4326" or "25832".
    """
    import re

    numbers = re.findall(r"[-+]?\d*\.?\d+", wkt)
    if not numbers:
        return "4326"
    max_val = max(abs(float(n)) for n in numbers)
    return "25832" if max_val > 1000 else "4326"


def _fetch_pvgis_monthly_blocking(
    latitude: float,
    longitude: float,
    tilt: float,
    azimuth: float,
    kwp: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Fetch production from PVGIS API via pvlib (blocking).

    Called exclusively via asyncio.to_thread — never called directly
    from async code paths.

    Args:
        latitude: Site latitude.
        longitude: Site longitude.
        tilt: Panel tilt in degrees.
        azimuth: Panel azimuth (0=south in PVGIS convention).
        kwp: Installed capacity in kWp.

    Returns:
        Tuple of (monthly_12, hourly_8760) numpy arrays in kWh.
        Both arrays are derived from the same data slice, ensuring
        monthly.sum() == hourly.sum().

    Raises:
        ConnectionError: If the PVGIS API is unreachable.
        ValueError: If the API returns invalid data.
    """
    from pvlib.iotools import get_pvgis_hourly

    result = get_pvgis_hourly(
        latitude=latitude,
        longitude=longitude,
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        pvcalculation=True,
        peakpower=kwp,
        loss=19,
        outputformat="json",
    )
    data = result[0]

    # Truncate to 8760 rows BEFORE any aggregation so monthly and hourly
    # are always derived from the same data slice (handles leap-year TMY)
    if len(data) > 8760:
        data = data.iloc[:8760]

    # Hourly kWh (P is in Watts, each point is 1 hour)
    hourly_kwh = (data["P"] / 1000.0).values

    # Pad if shorter than 8760 (shouldn't happen with standard PVGIS TMY)
    if len(hourly_kwh) < 8760:
        hourly_kwh = np.pad(hourly_kwh, (0, 8760 - len(hourly_kwh)))

    # Monthly aggregation from the same truncated data
    monthly_kwh = data["P"].resample("ME").sum() / 1000.0
    monthly_avg = monthly_kwh.groupby(monthly_kwh.index.month).mean()

    return monthly_avg.values, hourly_kwh


async def _fetch_pvgis_monthly(
    latitude: float,
    longitude: float,
    tilt: float,
    azimuth: float,
    kwp: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Async wrapper: offloads blocking pvlib call to thread pool."""
    return await asyncio.to_thread(
        _fetch_pvgis_monthly_blocking, latitude, longitude, tilt, azimuth, kwp
    )


async def fetch_production(system_input: SystemInput) -> ProductionData:
    """Get monthly PV production data for the given system.

    If system_input.annual_production_kwh is set, uses a synthetic solar
    distribution curve (no API call). Otherwise fetches real data from PVGIS,
    optionally combining with the Trentino Solar LIDAR API for shadow-corrected
    annual totals.

    Args:
        system_input: System parameters including location and capacity.

    Returns:
        ProductionData with 12-element monthly array.

    Raises:
        ConnectionError: If PVGIS is needed but unreachable.
    """
    if system_input.annual_production_kwh is not None:
        logger.info(
            "Using manual production override: %.1f kWh/year (synthetic distribution)",
            system_input.annual_production_kwh,
        )
        monthly = system_input.annual_production_kwh * SOLAR_MONTHLY_FRACTIONS
        return ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=system_input.annual_production_kwh,
            source="synthetic",
        )

    # Trentino hybrid path: LIDAR annual total + PVGIS monthly shape
    if (
        system_input.rooftop_wkt is not None
        and is_in_trentino(system_input.latitude, system_input.longitude)
    ):
        try:
            epsg = detect_epsg(system_input.rooftop_wkt)
            trentino = await fetch_trentino_solar(system_input.rooftop_wkt, epsg_code=epsg)
            annual_trentino = trentino.electrical_output_kwh

            pvgis_kwp = trentino.nominal_power_kwp
            monthly, hourly = await _fetch_pvgis_monthly(
                latitude=system_input.latitude,
                longitude=system_input.longitude,
                tilt=system_input.tilt,
                azimuth=system_input.azimuth,
                kwp=pvgis_kwp,
            )
            pvgis_annual = float(monthly.sum())
            if pvgis_annual <= 0:
                logger.warning("PVGIS returned zero annual production, falling back to synthetic")
                raise ValueError("PVGIS returned zero production")
            scale_factor = annual_trentino / pvgis_annual
            monthly = monthly * scale_factor
            hourly = hourly * scale_factor

            logger.info(
                "Hybrid Trentino+PVGIS: Trentino annual=%.0f kWh, "
                "PVGIS annual=%.0f kWh, scale=%.3f",
                annual_trentino,
                pvgis_annual,
                scale_factor,
            )

            return ProductionData(
                monthly_production_kwh=monthly,
                annual_production_kwh=annual_trentino,
                source="trentino+pvgis",
                effective_kwp=trentino.nominal_power_kwp,
                hourly_production_kwh=hourly,
            )
        except (ValueError, ConnectionError) as exc:
            logger.warning("Trentino Solar API failed, falling back to PVGIS: %s", exc)

    logger.info(
        "Fetching PVGIS data for lat=%.4f, lon=%.4f, tilt=%.1f, azimuth=%.1f, kWp=%.1f",
        system_input.latitude,
        system_input.longitude,
        system_input.tilt,
        system_input.azimuth,
        system_input.kwp,
    )
    monthly, hourly = await _fetch_pvgis_monthly(
        latitude=system_input.latitude,
        longitude=system_input.longitude,
        tilt=system_input.tilt,
        azimuth=system_input.azimuth,
        kwp=system_input.kwp,
    )
    annual = float(monthly.sum())
    return ProductionData(
        monthly_production_kwh=monthly,
        annual_production_kwh=annual,
        source="pvgis",
        hourly_production_kwh=hourly,
    )
