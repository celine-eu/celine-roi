"""Integration test for the full pipeline."""

from celine_roi.main import run_scenario
from celine_roi.models import ScenarioResult


class TestRunScenario:
    """End-to-end pipeline test with synthetic reference case."""

    def test_returns_scenario_result(self, reference_input, config) -> None:
        result = run_scenario(reference_input, config)
        assert isinstance(result, ScenarioResult)
        assert result.finance is not None
        assert result.validation is not None
        assert result.energy is not None
        assert result.incentives is not None

    def test_no_validation_fails(self, reference_input, config) -> None:
        result = run_scenario(reference_input, config)
        assert len(result.validation.fails) == 0, (
            f"Unexpected FAILs: {result.validation.fails}"
        )

    def test_npv_positive(self, reference_input, config) -> None:
        result = run_scenario(reference_input, config)
        assert result.finance.npv > 0

    def test_irr_above_wacc(self, reference_input, config) -> None:
        result = run_scenario(reference_input, config)
        assert result.finance.irr > config["wacc"]
