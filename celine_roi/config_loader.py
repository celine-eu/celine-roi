"""Load and merge YAML configuration files.

Config files live in a directory outside the package (typically config/).
This loader merges all YAML files in that directory into a single flat dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REQUIRED_KEYS = frozenset({
    "degradation", "lid", "retail_price", "energy_inflation",
    "general_inflation", "om_per_kwp", "insurance_rate", "wacc",
    "useful_life", "inverter_replacement_year",
    "sharing_ratio", "rid_tariff", "cer_tip", "cer_cacv",
    "cer_duration_years", "depreciation_coeff",
    "depreciation_first_year_factor", "ires", "irap",
})


def load_config(config_dir: Path) -> dict[str, Any]:
    """Load all YAML files from config_dir and merge into a single dict.

    Args:
        config_dir: Path to the directory containing YAML config files.

    Returns:
        Merged configuration dictionary.

    Raises:
        FileNotFoundError: If config_dir does not exist.
        ValueError: If required keys are missing after merge.
    """
    if not config_dir.is_dir():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    merged: dict[str, Any] = {}
    for yaml_file in sorted(config_dir.glob("*.yaml")):
        with open(yaml_file) as fh:
            data = yaml.safe_load(fh)
            if isinstance(data, dict):
                merged.update(data)

    missing = REQUIRED_KEYS - set(merged.keys())
    if missing:
        raise ValueError(f"Missing required config keys: {sorted(missing)}")

    return merged
