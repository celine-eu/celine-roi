"""CELINE ROI — Financial decision engine for Italian PV systems."""

from importlib.metadata import version

__version__ = version("celine-roi")

from celine.roi.config_loader import load_config, load_default_config
from celine.roi.engines.energy import compute_energy
from celine.roi.engines.finance import compute_finance
from celine.roi.engines.incentives import compute_incentives
from celine.roi.models import (
    ComparisonResult,
    EnergyResult,
    FinanceResult,
    IncentiveResult,
    ProductionData,
    ScenarioResult,
    SystemInput,
    ValidationReport,
)
from celine.roi.sdk import calculate_roi, calculate_roi_async

__all__ = [
    "__version__",
    "calculate_roi",
    "calculate_roi_async",
    "load_config",
    "load_default_config",
    "SystemInput",
    "ProductionData",
    "EnergyResult",
    "IncentiveResult",
    "FinanceResult",
    "ValidationReport",
    "ScenarioResult",
    "ComparisonResult",
    "compute_energy",
    "compute_incentives",
    "compute_finance",
]
