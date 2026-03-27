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

        With 49,500 kWh production and 40,000 kWh consumption (residential profile),
        hourly matching should yield ~20-45% self-consumption rate — NOT 71% from L1.
        """
        result = compute_energy(reference_input, hourly_production, config)
        assert result.tasso_autoconsumo < 0.50, (
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
