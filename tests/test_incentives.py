"""Tests for incentive engine.

Reference values from design spec (year 1, after LID):
- Production after LID: 48,757.50 kWh
- Autoconsumo: 35,256.58 kWh → Risparmio: 8,814.14 EUR
- Immissione: 13,500.92 kWh → RID: 945.06 EUR
- Condivisa: 7,425.51 kWh → CER TIP: 668.30 EUR, Cacv: 63.12 EUR
- Ammortamento: 2,025.00 EUR → Tax shield: 486.00 EUR
- IRES+IRAP: 467.74 EUR
"""

import pytest

from celine.roi.engines.energy import compute_energy
from celine.roi.engines.incentives import compute_incentives
from celine.roi.models import IncentiveResult, ProductionData, SystemInput


@pytest.fixture()
def energy_result(
    reference_input: SystemInput, reference_production: ProductionData, config: dict
):
    """Pre-computed energy result for reference case."""
    return compute_energy(reference_input, reference_production, config)


class TestComputeIncentivesYear1:
    """Year 1 values against hand-calculated reference."""

    def test_returns_incentive_result(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert isinstance(result, IncentiveResult)

    def test_arrays_length_equals_useful_life(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert len(result.years) == config["useful_life"]

    def test_production_degraded_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        expected = 49500.0 * (1 - 0.015)
        assert result.production_degraded[0] == pytest.approx(expected, rel=1e-3)

    def test_risparmio_autoconsumo_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.risparmio_autoconsumo[0] == pytest.approx(8814.14, rel=1e-2)

    def test_rid_revenue_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.rid_revenue[0] == pytest.approx(945.06, rel=1e-2)

    def test_cer_tip_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.cer_tip[0] == pytest.approx(668.30, rel=1e-2)

    def test_cer_cacv_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.cer_cacv[0] == pytest.approx(63.12, rel=1e-2)

    def test_ammortamento_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.ammortamento[0] == pytest.approx(2025.0, rel=1e-3)

    def test_tax_shield_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.tax_shield[0] == pytest.approx(486.0, rel=1e-3)

    def test_ires_irap_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.ires_irap[0] == pytest.approx(467.74, rel=1e-2)


class TestComputeIncentivesCER20Year:
    """CER incentive terminates after year 20."""

    def test_cer_tip_zero_after_year20(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert all(result.cer_tip[20:] == 0.0)

    def test_cer_cacv_zero_after_year20(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert all(result.cer_cacv[20:] == 0.0)

    def test_cer_tip_not_inflated(self, reference_input, energy_result, config) -> None:
        """CER TIP must be FIXED nominal — its ratio to cer_cacv must fall over time.

        Both cer_tip and cer_cacv share the same condivisa base each year.
        cer_tip uses a fixed tariff; cer_cacv is escalated by energy_inflation.
        Therefore cer_tip / cer_cacv must equal cer_tip_tariff / (cer_cacv_tariff * (1+inf)^(y-1)).
        If cer_tip were incorrectly inflated, the ratio would be constant instead of falling.
        """
        result = compute_incentives(reference_input, energy_result, config)
        cer_tip_tariff = config["cer_tip"]
        cer_cacv_tariff = config["cer_cacv"]
        inf = config["energy_inflation"]

        ratio_y1 = result.cer_tip[0] / result.cer_cacv[0]
        ratio_y10 = result.cer_tip[9] / result.cer_cacv[9]

        expected_y1 = cer_tip_tariff / (cer_cacv_tariff * (1 + inf) ** 0)
        expected_y10 = cer_tip_tariff / (cer_cacv_tariff * (1 + inf) ** 9)

        assert ratio_y1 == pytest.approx(expected_y1, rel=1e-4)
        assert ratio_y10 == pytest.approx(expected_y10, rel=1e-4)
        # Fixed-nominal means the ratio strictly decreases as cacv escalates
        assert ratio_y10 < ratio_y1


class TestComputeIncentivesDepreciation:
    """Depreciation schedule validation."""

    def test_depreciation_sums_to_capex(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.ammortamento.sum() == pytest.approx(45000.0, rel=1e-3)

    def test_depreciation_zero_after_full(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert all(result.ammortamento[12:] == 0.0)

    def test_year2_depreciation_full_rate(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.ammortamento[1] == pytest.approx(4050.0, rel=1e-3)


class TestComputeIncentivesDegradation:
    """Production degradation over system lifetime."""

    def test_production_decreases_over_time(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.production_degraded[-1] < result.production_degraded[0]

    def test_degradation_formula_year2(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        expected = 49500.0 * (1 - 0.015) * (1 - 0.0045) ** 1
        assert result.production_degraded[1] == pytest.approx(expected, rel=1e-4)

    def test_autoconsumo_not_taxed(self, reference_input, energy_result, config) -> None:
        """IRES+IRAP must be computed on RID+CER only, never on risparmio."""
        result = compute_incentives(reference_input, energy_result, config)
        taxable_y1 = result.rid_revenue[0] + result.cer_tip[0] + result.cer_cacv[0]
        tax_rate = config["ires"] + config["irap"]
        expected_tax = taxable_y1 * tax_rate
        assert result.ires_irap[0] == pytest.approx(expected_tax, rel=1e-3)
