"""Tests for the public Python API (sdk.py)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from celine.roi import (
    ScenarioResult,
    calculate_roi,
    calculate_roi_async,
    load_default_config,
)
from celine.roi.config_loader import REQUIRED_KEYS


def test_load_default_config_has_required_keys():
    config = load_default_config()
    missing = REQUIRED_KEYS - set(config.keys())
    assert not missing, f"Missing keys: {missing}"


def test_calculate_roi_returns_scenario_result():
    result = calculate_roi(
        kwp=6.0,
        latitude=45.93,
        longitude=11.27,
        capex=7500,
        annual_consumption_kwh=3000,
        user_type="residential",
        regime="RID_CER",
        annual_production_kwh=7200,
    )
    assert isinstance(result, ScenarioResult)
    assert result.finance.npv != 0
    assert 0 < result.finance.irr < 1
    assert result.finance.payback_simple > 0


async def test_calculate_roi_async():
    result = await calculate_roi_async(
        kwp=6.0,
        latitude=45.93,
        longitude=11.27,
        capex=7500,
        annual_consumption_kwh=3000,
        user_type="residential",
        regime="RID_CER",
        annual_production_kwh=7200,
    )
    assert isinstance(result, ScenarioResult)
    assert result.finance.npv != 0


def test_calculate_roi_with_config_overrides():
    base = calculate_roi(
        kwp=6.0,
        latitude=45.93,
        longitude=11.27,
        capex=7500,
        annual_consumption_kwh=3000,
        annual_production_kwh=7200,
    )
    overridden = calculate_roi(
        kwp=6.0,
        latitude=45.93,
        longitude=11.27,
        capex=7500,
        annual_consumption_kwh=3000,
        annual_production_kwh=7200,
        config_overrides={"wacc": 0.10},
    )
    assert overridden.finance.npv != base.finance.npv


def test_calculate_roi_event_loop_error():
    """Sync wrapper should raise when called from inside an event loop."""
    import asyncio

    async def _inner():
        calculate_roi(
            kwp=6.0,
            latitude=45.93,
            longitude=11.27,
            capex=7500,
            annual_consumption_kwh=3000,
            annual_production_kwh=7200,
        )

    with pytest.raises(RuntimeError, match="running event loop"):
        asyncio.run(_inner())


CONFIG_DIR = Path(__file__).parent.parent / "config"
BUNDLED_DIR = Path(__file__).parent.parent / "src" / "celine" / "roi" / "_default_config"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_bundled_config_matches_external():
    """Verify bundled _default_config files are in sync with config/."""
    for yaml_file in sorted(CONFIG_DIR.glob("*.yaml")):
        bundled = BUNDLED_DIR / yaml_file.name
        assert bundled.exists(), f"Missing bundled file: {yaml_file.name}"
        assert _file_hash(yaml_file) == _file_hash(bundled), (
            f"Config drift: {yaml_file.name} differs between config/ and _default_config/"
        )


def test_bundled_load_profiles_match_external():
    """Verify bundled load profile JSONs are in sync with config/load_profiles/."""
    ext_profiles = CONFIG_DIR / "load_profiles"
    bundled_profiles = BUNDLED_DIR / "load_profiles"
    for json_file in sorted(ext_profiles.glob("*.json")):
        bundled = bundled_profiles / json_file.name
        assert bundled.exists(), f"Missing bundled profile: {json_file.name}"
        assert _file_hash(json_file) == _file_hash(bundled), (
            f"Profile drift: {json_file.name} differs"
        )
