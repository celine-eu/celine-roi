"""Tests for hourly energy matching.

When hourly production data is available, the energy engine should:
1. Build an hourly consumption profile (8760 values)
2. Perform min(production_h, consumption_h) at each hour
3. Return 8760-element arrays
4. Produce realistic self-consumption rates (NOT the inflated L1 values)
"""

from __future__ import annotations

import numpy as np
import pytest

from celine.roi.engines.energy import compute_energy
from celine.roi.models import ProductionData, SystemInput


class TestHourlyEnergyMatching:
    """Tests for compute_energy with hourly resolution."""

    def test_returns_8760_arrays(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, hourly_production, config)
        assert len(result.production) == 8760
        assert len(result.consumption) == 8760
        assert len(result.autoconsumo) == 8760
        assert len(result.immissione) == 8760
        assert len(result.prelievo) == 8760
        assert len(result.energia_condivisa) == 8760

    def test_energy_balance_invariant_hourly(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        """autoconsumo + immissione == production (fundamental invariant)."""
        result = compute_energy(reference_input, hourly_production, config)
        total_auto = result.autoconsumo.sum()
        total_imm = result.immissione.sum()
        total_prod = result.production.sum()
        assert abs(total_auto + total_imm - total_prod) < 0.01

    def test_consumption_balance_hourly(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        """autoconsumo + prelievo == consumption."""
        result = compute_energy(reference_input, hourly_production, config)
        total_auto = result.autoconsumo.sum()
        total_prel = result.prelievo.sum()
        total_cons = result.consumption.sum()
        assert abs(total_auto + total_prel - total_cons) < 0.01

    def test_autoconsumo_rate_realistic(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        """Hourly matching should produce a LOWER autoconsumo rate than flat monthly.

        With 49,500 kWh production and 40,000 kWh consumption (commercial profile),
        hourly matching should yield ~45-65% self-consumption rate — NOT 71% from L1.
        The reference_input uses user_type="commercial" which gets a daytime-peak
        load profile, so overlap with PV production is higher than residential.
        """
        result = compute_energy(reference_input, hourly_production, config)
        assert result.tasso_autoconsumo < 0.70, (
            f"Hourly autoconsumo rate {result.tasso_autoconsumo:.1%} is suspiciously high"
        )
        assert result.tasso_autoconsumo > 0.10, (
            f"Hourly autoconsumo rate {result.tasso_autoconsumo:.1%} is suspiciously low"
        )

    def test_prelievo_is_nonzero_hourly(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        """With hourly matching, there MUST be grid withdrawal (nighttime consumption)."""
        result = compute_energy(reference_input, hourly_production, config)
        assert result.prelievo.sum() > 0, (
            "Prelievo is zero — hourly matching should show nighttime grid withdrawal"
        )

    def test_autoconsumo_never_exceeds_production_hourly(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, hourly_production, config)
        assert np.all(result.autoconsumo <= result.production + 0.01)

    def test_autoconsumo_never_exceeds_consumption_hourly(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, hourly_production, config)
        assert np.all(result.autoconsumo <= result.consumption + 0.01)

    def test_immissione_non_negative_hourly(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, hourly_production, config)
        assert np.all(result.immissione >= -0.01)

    def test_annual_production_total(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, hourly_production, config)
        assert result.production.sum() == pytest.approx(49500.0, rel=1e-3)

    def test_annual_consumption_total(
        self, reference_input: SystemInput, hourly_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, hourly_production, config)
        assert result.consumption.sum() == pytest.approx(40000.0, rel=1e-3)


class TestHourlyFallbackToMonthly:
    """When hourly data is NOT available, the engine falls back to monthly."""

    def test_monthly_fallback_12_elements(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        """Without hourly_production_kwh, engine uses L1 monthly matching."""
        result = compute_energy(reference_input, reference_production, config)
        assert len(result.production) == 12

    def test_monthly_fallback_values_unchanged(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        """L1 monthly values must be identical to previous behavior."""
        result = compute_energy(reference_input, reference_production, config)
        assert result.autoconsumo.sum() == pytest.approx(35387.39, rel=1e-3)
        assert result.tasso_autoconsumo == pytest.approx(0.7149, rel=1e-3)


class TestProfileRoutingByUserType:
    """Verify that user_type selects the correct load profile."""

    def test_commercial_higher_autoconsumo_than_residential(
        self, hourly_production: ProductionData, config: dict
    ) -> None:
        """Commercial daytime profile should overlap more with PV than residential evening."""
        base_kwargs = dict(
            kwp=10.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=12000.0, annual_consumption_kwh=8000.0,
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            annual_production_kwh=12000.0,
        )
        hourly = hourly_production.hourly_production_kwh * (12000.0 / 49500.0)
        monthly = hourly_production.monthly_production_kwh * (12000.0 / 49500.0)
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=12000.0,
            source="synthetic",
            hourly_production_kwh=hourly,
        )

        si_res = SystemInput(**base_kwargs, user_type="residential")
        si_com = SystemInput(**base_kwargs, user_type="commercial")

        res_result = compute_energy(si_res, pd, config)
        com_result = compute_energy(si_com, pd, config)

        assert com_result.tasso_autoconsumo > res_result.tasso_autoconsumo, (
            f"Commercial ({com_result.tasso_autoconsumo:.1%}) should exceed "
            f"residential ({res_result.tasso_autoconsumo:.1%})"
        )

    def test_industrial_higher_autoconsumo_than_residential(
        self, hourly_production: ProductionData, config: dict
    ) -> None:
        """Industrial flat profile should overlap more with PV than residential evening."""
        base_kwargs = dict(
            kwp=10.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=12000.0, annual_consumption_kwh=8000.0,
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            annual_production_kwh=12000.0,
        )
        hourly = hourly_production.hourly_production_kwh * (12000.0 / 49500.0)
        monthly = hourly_production.monthly_production_kwh * (12000.0 / 49500.0)
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=12000.0,
            source="synthetic",
            hourly_production_kwh=hourly,
        )

        si_res = SystemInput(**base_kwargs, user_type="residential")
        si_ind = SystemInput(**base_kwargs, user_type="industrial")

        res_result = compute_energy(si_res, pd, config)
        ind_result = compute_energy(si_ind, pd, config)

        assert ind_result.tasso_autoconsumo > res_result.tasso_autoconsumo, (
            f"Industrial ({ind_result.tasso_autoconsumo:.1%}) should exceed "
            f"residential ({res_result.tasso_autoconsumo:.1%})"
        )

    def test_load_profile_override_wins_over_type_mapping(
        self, hourly_production: ProductionData, config: dict
    ) -> None:
        """Explicit load_profile in config should override the type-based mapping."""
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

        # Default residential profile
        res_result = compute_energy(si, pd, config)

        # Force heat pump profile via override (should override type mapping)
        override_config = {**config, "load_profile": "residential_heat_pump.json"}
        override_config.pop("load_profile_by_type", None)
        hp_result = compute_energy(si, pd, override_config)

        assert hp_result.tasso_autoconsumo > res_result.tasso_autoconsumo, (
            "Heat pump override should produce higher autoconsumo than default residential"
        )
