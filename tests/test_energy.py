"""Tests for energy matching engine.

The energy engine operates on NAMEPLATE production (49,500 kWh), BEFORE
any degradation (LID/annual). Degradation is applied by the incentive engine.

Pre-LID reference values (energy engine output on 49,500 kWh):
- Autoconsumo: 35,387.39 kWh
- Immissione: 14,112.61 kWh
- Tasso autoconsumo: 71.49%
- Condivisa (55%): 7,761.94 kWh

Post-LID values (35,256.58 / 13,500.92) are tested in test_incentives.py.
"""

import numpy as np
import pytest

from celine.roi.engines.energy import compute_energy
from celine.roi.models import EnergyResult, ProductionData, SystemInput


class TestComputeEnergy:
    """Tests for compute_energy with synthetic reference case.

    @verifies REQ-0102 REQ-0103 REQ-0104 REQ-0105
    """

    def test_returns_energy_result(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        assert isinstance(result, EnergyResult)

    def test_arrays_have_12_elements(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        assert len(result.production) == 12
        assert len(result.consumption) == 12
        assert len(result.autoconsumo) == 12
        assert len(result.immissione) == 12
        assert len(result.prelievo) == 12
        assert len(result.energia_condivisa) == 12

    def test_energy_balance_invariant(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        """autoconsumo + immissione == production (fundamental invariant)."""
        result = compute_energy(reference_input, reference_production, config)
        total_auto = result.autoconsumo.sum()
        total_imm = result.immissione.sum()
        total_prod = result.production.sum()
        assert abs(total_auto + total_imm - total_prod) < 0.01

    def test_consumption_balance(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        """autoconsumo + prelievo == consumption."""
        result = compute_energy(reference_input, reference_production, config)
        total_auto = result.autoconsumo.sum()
        total_prel = result.prelievo.sum()
        total_cons = result.consumption.sum()
        assert abs(total_auto + total_prel - total_cons) < 0.01

    def test_production_total(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        assert abs(result.production.sum() - 49500.0) < 0.01

    def test_consumption_flat_l1(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        expected_monthly = 40000.0 / 12
        for month_val in result.consumption:
            assert abs(month_val - expected_monthly) < 0.01

    def test_autoconsumo_never_exceeds_production(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        assert np.all(result.autoconsumo <= result.production + 0.01)

    def test_autoconsumo_never_exceeds_consumption(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        assert np.all(result.autoconsumo <= result.consumption + 0.01)

    def test_immissione_non_negative(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        assert np.all(result.immissione >= -0.01)

    def test_energia_condivisa_within_immissione(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        assert result.energia_condivisa.sum() <= result.immissione.sum() + 0.01

    def test_sharing_ratio_applied(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        expected = result.immissione * config["sharing_ratio"]
        np.testing.assert_allclose(result.energia_condivisa, expected, atol=0.01)

    def test_autoconsumo_total_nameplate(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        """Autoconsumo on 49,500 kWh nameplate (pre-LID)."""
        result = compute_energy(reference_input, reference_production, config)
        assert result.autoconsumo.sum() == pytest.approx(35387.39, rel=1e-3)

    def test_immissione_total_nameplate(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        """Immissione on 49,500 kWh nameplate (pre-LID)."""
        result = compute_energy(reference_input, reference_production, config)
        assert result.immissione.sum() == pytest.approx(14112.61, rel=1e-3)

    def test_tasso_autoconsumo_nameplate(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        assert result.tasso_autoconsumo == pytest.approx(0.7149, rel=1e-3)

    def test_tasso_autoconsumo_in_range(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        result = compute_energy(reference_input, reference_production, config)
        assert 0.0 <= result.tasso_autoconsumo <= 1.0

    def test_cer_virtual_consumption_rate_reduction(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        """With cer_virtual_consumption_rate=0.5, energia_condivisa should be halved."""
        result_default = compute_energy(reference_input, reference_production, config)

        config_reduced = {**config, "cer_virtual_consumption_rate": 0.5}
        result_reduced = compute_energy(reference_input, reference_production, config_reduced)

        expected_condivisa = result_default.energia_condivisa * 0.5
        np.testing.assert_allclose(result_reduced.energia_condivisa, expected_condivisa, atol=0.01)

    def test_cer_virtual_consumption_rate_backward_compatible(
        self, reference_input: SystemInput, reference_production: ProductionData, config: dict
    ) -> None:
        """With cer_virtual_consumption_rate=1.0 (default), behavior should match original."""
        config_with_rate = {**config, "cer_virtual_consumption_rate": 1.0}
        result_with_rate = compute_energy(reference_input, reference_production, config_with_rate)
        result_default = compute_energy(reference_input, reference_production, config)

        np.testing.assert_allclose(
            result_with_rate.energia_condivisa,
            result_default.energia_condivisa,
            atol=0.01
        )


class TestComputeEnergyEdgeCases:
    """Edge case tests for energy engine.

    @verifies REQ-0109
    """

    def test_zero_consumption(self, config: dict) -> None:
        """All production goes to grid."""
        si = SystemInput(
            kwp=10.0, latitude=45.0, longitude=11.0, tilt=30.0, azimuth=0.0,
            capex=10000.0, annual_consumption_kwh=0.0, user_type="commercial",
            regime="RID", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            annual_production_kwh=10000.0,
        )
        from celine.roi.pvgis_client import SOLAR_MONTHLY_FRACTIONS
        monthly = 10000.0 * SOLAR_MONTHLY_FRACTIONS
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=10000.0,
            source="synthetic"
        )
        result = compute_energy(si, pd, config)
        assert abs(result.autoconsumo.sum()) < 0.01
        assert abs(result.immissione.sum() - 10000.0) < 0.01
        assert result.tasso_autoconsumo == pytest.approx(0.0, abs=0.001)

    def test_consumption_exceeds_production(self, config: dict) -> None:
        """All production self-consumed, no export."""
        si = SystemInput(
            kwp=5.0, latitude=45.0, longitude=11.0, tilt=30.0, azimuth=0.0,
            capex=5000.0, annual_consumption_kwh=100000.0, user_type="industrial",
            regime="RID", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
            annual_production_kwh=5000.0,
        )
        from celine.roi.pvgis_client import SOLAR_MONTHLY_FRACTIONS
        monthly = 5000.0 * SOLAR_MONTHLY_FRACTIONS
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=5000.0,
            source="synthetic"
        )
        result = compute_energy(si, pd, config)
        assert abs(result.immissione.sum()) < 0.01
        assert abs(result.autoconsumo.sum() - 5000.0) < 0.01
        assert result.tasso_autoconsumo == pytest.approx(1.0, abs=0.001)
