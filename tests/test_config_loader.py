"""Tests for YAML config loading and validation."""

from pathlib import Path

import pytest

from celine.roi.config_loader import load_config

CONFIG_DIR = Path(__file__).parent.parent / "config"


class TestLoadConfig:
    """Tests for load_config function.

    @verifies REQ-0801
    """

    def test_loads_all_yaml_files(self) -> None:
        config = load_config(CONFIG_DIR)
        assert "degradation" in config
        assert "wacc" in config
        assert "cer_tip" in config
        assert "rid_tariff" in config
        assert "ires" in config
        assert "irap" in config

    def test_values_match_yaml(self) -> None:
        config = load_config(CONFIG_DIR)
        assert config["degradation"] == 0.0045
        assert config["ires"] == 0.24
        assert config["cer_tip"] == 0.09

    def test_missing_directory_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/path"))

    def test_required_keys_present(self) -> None:
        config = load_config(CONFIG_DIR)
        required = [
            "degradation", "lid", "retail_price", "energy_inflation",
            "general_inflation", "om_per_kwp", "insurance_rate", "wacc",
            "useful_life", "inverter_replacement_year",
            "sharing_ratio", "rid_tariff", "cer_tip", "cer_cacv",
            "cer_duration_years", "depreciation_coeff",
            "depreciation_first_year_factor", "ires", "irap",
        ]
        for key in required:
            assert key in config, f"Missing required config key: {key}"
