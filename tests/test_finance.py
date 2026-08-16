"""Tests for finance engine.

Reference case: 45 kWp, 45,000 EUR CAPEX, 100% equity, 5.5% WACC.
"""

import numpy_financial as npf
import pytest

from celine.roi.engines.energy import compute_energy
from celine.roi.engines.finance import compute_finance
from celine.roi.engines.incentives import compute_incentives
from celine.roi.models import FinanceResult, ProductionData, SystemInput
from celine.roi.pvgis_client import SOLAR_MONTHLY_FRACTIONS


@pytest.fixture()
def incentive_result(
    reference_input: SystemInput, reference_production: ProductionData, config: dict
):
    """Pre-computed incentive result for reference case."""
    energy = compute_energy(reference_input, reference_production, config)
    return compute_incentives(reference_input, energy, config)


class TestComputeFinance:
    """Core finance engine tests.

    @verifies REQ-0601 REQ-0603 REQ-0604
    """

    def test_returns_finance_result(
        self, reference_input, incentive_result, config
    ) -> None:
        result = compute_finance(reference_input, incentive_result, config)
        assert isinstance(result, FinanceResult)

    def test_cashflows_length(
        self, reference_input, incentive_result, config
    ) -> None:
        """26 entries: year 0 (investment) + years 1-25."""
        result = compute_finance(reference_input, incentive_result, config)
        assert len(result.cashflows) == config["useful_life"] + 1

    def test_year0_equals_negative_equity_contribution(
        self, reference_input, incentive_result, config
    ) -> None:
        """Year 0 = -CAPEX * equity_fraction."""
        result = compute_finance(reference_input, incentive_result, config)
        expected = -reference_input.capex * reference_input.equity_fraction
        assert result.cashflows[0] == pytest.approx(expected)

    def test_npv_positive(self, reference_input, incentive_result, config) -> None:
        result = compute_finance(reference_input, incentive_result, config)
        assert result.npv > 0

    def test_irr_reasonable(self, reference_input, incentive_result, config) -> None:
        result = compute_finance(reference_input, incentive_result, config)
        assert 0.05 < result.irr < 0.30

    def test_payback_simple_reasonable(self, reference_input, incentive_result, config) -> None:
        result = compute_finance(reference_input, incentive_result, config)
        assert 3.0 < result.payback_simple < 9.0

    def test_payback_discounted_longer_than_simple(
        self, reference_input, incentive_result, config
    ) -> None:
        result = compute_finance(reference_input, incentive_result, config)
        assert result.payback_discounted >= result.payback_simple

    def test_dscr_none_for_equity(self, reference_input, incentive_result, config) -> None:
        result = compute_finance(reference_input, incentive_result, config)
        assert result.dscr is None

    def test_cumulative_ends_positive(self, reference_input, incentive_result, config) -> None:
        result = compute_finance(reference_input, incentive_result, config)
        assert result.cumulative[-1] > 0


class TestFinanceInvariants:
    """Mathematical invariant checks.

    @verifies REQ-0602 REQ-0605
    """

    def test_npv_at_zero_equals_sum_of_cashflows(
        self, reference_input, incentive_result, config
    ) -> None:
        result = compute_finance(reference_input, incentive_result, config)
        npv_zero = float(npf.npv(0.0, result.cashflows))
        cashflow_sum = float(result.cashflows.sum())
        assert npv_zero == pytest.approx(cashflow_sum, rel=0.01)

    def test_inverter_replacement_in_year12(
        self, reference_input, incentive_result, config
    ) -> None:
        result = compute_finance(reference_input, incentive_result, config)
        assert result.cashflows[12] < result.cashflows[11]


class TestFinanceWithLoan:
    """Tests for financed scenarios.

    @verifies REQ-0601 REQ-0604
    """

    def test_year0_reflects_equity_only(self, config) -> None:
        si = SystemInput(
            kwp=45.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=45000.0, annual_consumption_kwh=40000.0, user_type="commercial",
            regime="RID_CER", equity_fraction=0.3, loan_rate=0.05,
            loan_duration_years=15, annual_production_kwh=49500.0,
        )
        monthly = 49500.0 * SOLAR_MONTHLY_FRACTIONS
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=49500.0,
            source="synthetic"
        )
        energy = compute_energy(si, pd, config)
        incentives = compute_incentives(si, energy, config)
        result = compute_finance(si, incentives, config)
        assert result.cashflows[0] == pytest.approx(-13500.0)

    def test_dscr_not_none_when_financed(self, config) -> None:
        si = SystemInput(
            kwp=45.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=45000.0, annual_consumption_kwh=40000.0, user_type="commercial",
            regime="RID_CER", equity_fraction=0.3, loan_rate=0.05,
            loan_duration_years=15, annual_production_kwh=49500.0,
        )
        monthly = 49500.0 * SOLAR_MONTHLY_FRACTIONS
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=49500.0,
            source="synthetic"
        )
        energy = compute_energy(si, pd, config)
        incentives = compute_incentives(si, energy, config)
        result = compute_finance(si, incentives, config)
        assert result.dscr is not None
        assert len(result.dscr) == 15


class TestFinanceWithDetrazione:
    """Finance engine correctly includes detrazione IRPEF in cashflows.

    @verifies REQ-0606
    """

    def test_residential_cashflow_includes_detrazione(self, config) -> None:
        """Residential system cashflows should include detrazione credit."""
        si = SystemInput(
            kwp=6.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=8400.0, annual_consumption_kwh=3500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=7200.0,
            abitazione_principale=True,
        )
        monthly = 7200.0 * SOLAR_MONTHLY_FRACTIONS
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=7200.0,
            source="synthetic",
        )
        energy = compute_energy(si, pd, config)
        incentives = compute_incentives(si, energy, config)
        result = compute_finance(si, incentives, config)

        # Detrazione adds 8400*0.50/10 = 420 EUR/yr for 10 years
        assert result.cashflows[1] > 0
        assert result.npv > 0, "Residential with detrazione should have positive NPV"

    def test_commercial_finance_unchanged(
        self, reference_input, incentive_result, config
    ) -> None:
        """Commercial finance results should be unchanged (no detrazione)."""
        result = compute_finance(reference_input, incentive_result, config)
        assert result.npv > 0
        assert result.cashflows[1] > 0
