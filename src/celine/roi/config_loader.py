"""Load and merge YAML configuration files.

Config files live in a directory outside the package (typically config/).
This loader merges all YAML files in that directory into a single flat dict.
For library usage, bundled defaults are available via load_default_config().
"""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

REQUIRED_KEYS = frozenset({
    "degradation", "lid", "retail_price", "energy_inflation",
    "general_inflation", "om_per_kwp", "insurance_rate", "wacc",
    "useful_life", "inverter_replacement_year",
    "sharing_ratio", "rid_tariff", "cer_tip", "cer_cacv",
    "cer_duration_years", "cer_libero_ratio", "depreciation_coeff",
    "depreciation_first_year_factor", "ires", "irap",
})


def _bundled_config_path() -> Path:
    """Return the filesystem path to the bundled _default_config directory."""
    return Path(str(resources.files("celine.roi._default_config")))


def resolve_config_dir(explicit: Path | None = None) -> Path:
    """Resolve the config directory using a fallback chain.

    1. explicit argument (if provided)
    2. CELINE_CONFIG_DIR environment variable
    3. Bundled _default_config inside the package
    """
    if explicit is not None:
        return explicit
    env = os.environ.get("CELINE_CONFIG_DIR")
    if env:
        return Path(env)
    return _bundled_config_path()


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


def load_default_config() -> dict[str, Any]:
    """Load bundled default configuration shipped inside the package.

    Uses importlib.resources to read YAML files from celine.roi._default_config.
    This is the primary config source for library/SDK usage.
    Server deployments should use load_config(config_dir) with external YAML files.

    Returns:
        Merged configuration dictionary with all default values.
    """
    return load_config(_bundled_config_path())
