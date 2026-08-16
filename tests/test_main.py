"""Integration test for the full pipeline."""

import pytest

from celine.roi.main import run_scenario
from celine.roi.models import ScenarioResult, SystemInput


class TestRunScenario:
    """End-to-end pipeline test with synthetic reference case.

    @verifies REQ-0101
    """

    async def test_returns_scenario_result(self, reference_input, config) -> None:
        result = await run_scenario(reference_input, config)
        assert isinstance(result, ScenarioResult)
        assert result.finance is not None
        assert result.validation is not None
        assert result.energy is not None
        assert result.incentives is not None

    async def test_no_validation_fails(self, reference_input, config) -> None:
        result = await run_scenario(reference_input, config)
        assert len(result.validation.fails) == 0, (
            f"Unexpected FAILs: {result.validation.fails}"
        )

    async def test_npv_positive(self, reference_input, config) -> None:
        result = await run_scenario(reference_input, config)
        assert result.finance.npv > 0

    async def test_irr_above_wacc(self, reference_input, config) -> None:
        result = await run_scenario(reference_input, config)
        assert result.finance.irr > config["wacc"]

    async def test_battery_cost_deduction(self, reference_input, config) -> None:
        """Battery cost (power law) should be deducted from CAPEX."""
        battery_kwh = 10.0
        original_capex = 15000.0

        # Power law: cost = base * kwh^exponent
        base = config.get("battery_cost_base", 2400.0)
        exponent = config.get("battery_cost_exponent", 0.53)
        floor = config.get("battery_cost_floor", 1500.0)
        expected_battery_cost = max(floor, base * (battery_kwh ** exponent))
        expected_pv_capex = original_capex - expected_battery_cost

        input_with_battery = SystemInput(
            kwp=45.0,
            latitude=45.9333,
            longitude=11.2667,
            tilt=30.0,
            azimuth=0.0,
            capex=original_capex,
            annual_consumption_kwh=40000.0,
            user_type="commercial",
            regime="RID_CER",
            equity_fraction=1.0,
            loan_rate=0.0,
            loan_duration_years=0,
            annual_production_kwh=49500.0,
            battery_kwh=battery_kwh,
        )

        result = await run_scenario(input_with_battery, config)
        assert result.system_input.capex == pytest.approx(expected_pv_capex, rel=1e-3)

    async def test_battery_cost_deduction_no_battery(self, reference_input, config) -> None:
        """With battery_kwh=0, CAPEX should remain unchanged."""
        result = await run_scenario(reference_input, config)
        assert result.system_input.capex == reference_input.capex
