"""Tests for the scenario comparator."""

from __future__ import annotations

from pathlib import Path

import pytest

from celine.roi.config_loader import load_config
from celine.roi.models import ComparisonResult, ScenarioResult, SystemInput
from celine.roi.scenarios.comparator import _split_overrides, compare_scenarios

CONFIG_DIR = Path(__file__).parent.parent / "config"


@pytest.fixture()
def base_input() -> SystemInput:
    return SystemInput(
        kwp=45.0, latitude=45.9333, longitude=11.2667, tilt=30.0, azimuth=0.0,
        capex=45000.0, annual_consumption_kwh=40000.0, user_type="commercial",
        regime="RID_CER", equity_fraction=1.0, loan_rate=0.0, loan_duration_years=0,
        annual_production_kwh=49500.0, location="Lavarone, Trentino",
    )


@pytest.fixture()
def base_config() -> dict:
    return load_config(CONFIG_DIR)


class TestSplitOverrides:
    def test_system_keys_separated(self) -> None:
        overrides = {"regime": "RID", "capex": 50000.0, "wacc": 0.06}
        sys_ov, cfg_ov = _split_overrides(overrides)
        assert sys_ov == {"regime": "RID", "capex": 50000.0}
        assert cfg_ov == {"wacc": 0.06}

    def test_empty_overrides(self) -> None:
        sys_ov, cfg_ov = _split_overrides({})
        assert sys_ov == {}
        assert cfg_ov == {}

    def test_all_config_keys(self) -> None:
        overrides = {"wacc": 0.08, "retail_price": 0.30}
        sys_ov, cfg_ov = _split_overrides(overrides)
        assert sys_ov == {}
        assert cfg_ov == overrides

    def test_all_system_keys(self) -> None:
        overrides = {"regime": "RID", "equity_fraction": 0.7}
        sys_ov, cfg_ov = _split_overrides(overrides)
        assert sys_ov == overrides
        assert cfg_ov == {}


class TestCompareScenarios:
    @pytest.mark.asyncio
    async def test_base_case_only(self, base_input: SystemInput, base_config: dict) -> None:
        result = await compare_scenarios(base_input, base_config, {"Base": {}})
        assert isinstance(result, ComparisonResult)
        assert "Base" in result.scenarios
        assert len(result.scenarios) == 1
        assert isinstance(result.scenarios["Base"], ScenarioResult)
        assert "VAN" in result.summary_table

    @pytest.mark.asyncio
    async def test_two_scenarios_different_npv(
        self, base_input: SystemInput, base_config: dict,
    ) -> None:
        result = await compare_scenarios(
            base_input, base_config,
            {"Base RID+CER": {}, "Solo RID": {"regime": "RID"}},
        )
        assert len(result.scenarios) == 2
        npv_cer = result.scenarios["Base RID+CER"].finance.npv
        npv_rid = result.scenarios["Solo RID"].finance.npv
        assert npv_cer != npv_rid

    @pytest.mark.asyncio
    async def test_config_override_changes_result(
        self, base_input: SystemInput, base_config: dict,
    ) -> None:
        result = await compare_scenarios(
            base_input, base_config,
            {"Standard": {}, "Prezzo alto": {"retail_price": 0.35}},
        )
        base_risparmio = float(result.scenarios["Standard"].incentives.risparmio_autoconsumo[0])
        high_risparmio = float(result.scenarios["Prezzo alto"].incentives.risparmio_autoconsumo[0])
        assert high_risparmio > base_risparmio

    @pytest.mark.asyncio
    async def test_mixed_overrides(self, base_input: SystemInput, base_config: dict) -> None:
        result = await compare_scenarios(
            base_input, base_config,
            {"Base": {}, "Pessimistico": {"regime": "RID", "wacc": 0.08}},
        )
        assert result.scenarios["Pessimistico"].finance.npv < result.scenarios["Base"].finance.npv

    @pytest.mark.asyncio
    async def test_summary_contains_scenario_names(
        self, base_input: SystemInput, base_config: dict,
    ) -> None:
        result = await compare_scenarios(
            base_input, base_config,
            {"Alpha": {}, "Beta": {"regime": "RID"}},
        )
        assert "Alpha" in result.summary_table
        assert "Beta" in result.summary_table

    @pytest.mark.asyncio
    async def test_summary_has_delta_column(
        self, base_input: SystemInput, base_config: dict,
    ) -> None:
        result = await compare_scenarios(
            base_input, base_config,
            {"Base": {}, "Alt": {"regime": "RID"}},
        )
        assert "Δ" in result.summary_table

    @pytest.mark.asyncio
    async def test_invalid_override_key_raises(
        self, base_input: SystemInput, base_config: dict,
    ) -> None:
        with pytest.raises(ValueError, match="Unknown override"):
            await compare_scenarios(base_input, base_config, {"Bad": {"nonexistent_key_xyz": 42}})

    @pytest.mark.asyncio
    async def test_empty_scenarios_raises(self, base_input: SystemInput, base_config: dict) -> None:
        with pytest.raises(ValueError, match="At least one scenario"):
            await compare_scenarios(base_input, base_config, {})
