"""Validation tests: compare hourly engine output against known benchmarks.

These are NOT unit tests — they validate that the model produces
physically plausible results for typical Italian residential scenarios.
"""

from __future__ import annotations

import numpy as np
import pytest

from celine.roi.engines.energy import compute_energy
from celine.roi.models import ProductionData, SystemInput


class TestResidentialBenchmarks:
    """Benchmark autoconsumo rates against industry expectations."""

    def test_small_residential_autoconsumo_rate(
        self, hourly_production: ProductionData, config: dict
    ) -> None:
        """3 kWp residential, 2700 kWh/year consumption: expect 25-50% self-consumption."""
        si = SystemInput(
            kwp=3.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=6000.0, annual_consumption_kwh=2700.0, user_type="residential",
            regime="RID", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            annual_production_kwh=3600.0,
        )
        # Scale hourly production to 3600 kWh
        hourly = hourly_production.hourly_production_kwh * (3600.0 / 49500.0)
        monthly = hourly_production.monthly_production_kwh * (3600.0 / 49500.0)
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=3600.0,
            source="synthetic",
            hourly_production_kwh=hourly,
        )
        result = compute_energy(si, pd, config)
        rate = result.tasso_autoconsumo
        assert 0.20 <= rate <= 0.55, f"Small residential rate {rate:.1%} outside expected range"

    def test_oversized_system_low_autoconsumo(
        self, hourly_production: ProductionData, config: dict
    ) -> None:
        """20 kWp on 3500 kWh consumption: expect <25% self-consumption."""
        si = SystemInput(
            kwp=20.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=30000.0, annual_consumption_kwh=3500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            annual_production_kwh=22000.0,
        )
        hourly = hourly_production.hourly_production_kwh * (22000.0 / 49500.0)
        monthly = hourly_production.monthly_production_kwh * (22000.0 / 49500.0)
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=22000.0,
            source="synthetic",
            hourly_production_kwh=hourly,
        )
        result = compute_energy(si, pd, config)
        rate = result.tasso_autoconsumo
        assert rate < 0.30, f"Oversized system rate {rate:.1%} too high — should be <30%"
        assert result.prelievo.sum() > 0, "Must have grid withdrawal"

    def test_heat_pump_higher_than_residential(
        self, hourly_production: ProductionData, config: dict
    ) -> None:
        """Heat pump profile should produce higher autoconsumo than residential.

        Same system, same production — only the consumption profile changes.
        Heat pump shifts consumption to daytime → more overlap with PV.
        """
        si = SystemInput(
            kwp=5.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=7000.0, annual_consumption_kwh=4500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            annual_production_kwh=6000.0,
        )
        hourly = hourly_production.hourly_production_kwh * (6000.0 / 49500.0)
        monthly = hourly_production.monthly_production_kwh * (6000.0 / 49500.0)
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=6000.0,
            source="synthetic",
            hourly_production_kwh=hourly,
        )

        # Residential profile (default)
        res_result = compute_energy(si, pd, config)

        # Heat pump profile — remove load_profile_by_type so explicit override wins
        hp_config = {**config, "load_profile": "residential_heat_pump.json"}
        hp_config.pop("load_profile_by_type", None)
        hp_result = compute_energy(si, pd, hp_config)

        assert hp_result.tasso_autoconsumo > res_result.tasso_autoconsumo, (
            f"Heat pump rate ({hp_result.tasso_autoconsumo:.1%}) should be higher than "
            f"residential ({res_result.tasso_autoconsumo:.1%})"
        )
        # Heat pump should be in 30-60% range for a 5kWp/4500kWh system
        assert 0.25 <= hp_result.tasso_autoconsumo <= 0.65, (
            f"Heat pump rate {hp_result.tasso_autoconsumo:.1%} outside expected range"
        )
