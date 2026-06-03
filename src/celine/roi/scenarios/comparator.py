"""Scenario comparator — run N named scenarios and produce a side-by-side table.

Each scenario applies arbitrary overrides to SystemInput fields and/or config
keys.  The comparator reuses PVGIS production data when location/capacity
fields are unchanged, saving ~2-5 s per scenario.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
from typing import Any

import numpy as np

from celine.roi.engines.energy import compute_energy
from celine.roi.engines.finance import compute_finance
from celine.roi.engines.incentives import compute_incentives
from celine.roi.models import (
    ComparisonResult,
    ProductionData,
    ScenarioResult,
    SystemInput,
)
from celine.roi.pvgis_client import fetch_production
from celine.roi.validation.warnings import validate_model

logger = logging.getLogger(__name__)

# Fields on SystemInput determined at runtime so the split stays in sync
# with the dataclass definition even when new fields are added.
_SYSTEM_FIELDS: frozenset[str] = frozenset(
    f.name for f in dataclasses.fields(SystemInput)
)

# Overriding any of these forces a fresh PVGIS / production fetch.
_PRODUCTION_AFFECTING_FIELDS: frozenset[str] = frozenset({
    "latitude",
    "longitude",
    "tilt",
    "azimuth",
    "kwp",
    "rooftop_wkt",
    "annual_production_kwh",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_overrides(
    overrides: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split an override dict into SystemInput keys vs config keys.

    Args:
        overrides: Flat dict of override key/value pairs.

    Returns:
        Tuple of (system_overrides, config_overrides).
    """
    system_overrides: dict[str, Any] = {}
    config_overrides: dict[str, Any] = {}
    for key, value in overrides.items():
        if key in _SYSTEM_FIELDS:
            system_overrides[key] = value
        else:
            config_overrides[key] = value
    return system_overrides, config_overrides


def _validate_override_keys(
    overrides: dict[str, Any],
    valid_config_keys: frozenset[str],
) -> None:
    """Raise ValueError if any override key is unrecognised.

    Args:
        overrides: Flat dict of override key/value pairs.
        valid_config_keys: Set of keys present in the loaded config dict.

    Raises:
        ValueError: If an override key is neither a SystemInput field
            nor a known config key.
    """
    for key in overrides:
        if key not in _SYSTEM_FIELDS and key not in valid_config_keys:
            raise ValueError(
                f"Unknown override key: '{key}'. "
                f"Must be a SystemInput field or a config key."
            )


def _apply_overrides(
    base_input: SystemInput,
    base_config: dict[str, Any],
    overrides: dict[str, Any],
) -> tuple[SystemInput, dict[str, Any]]:
    """Deep-copy base objects and apply overrides.

    Args:
        base_input: Original system input (frozen dataclass).
        base_config: Original merged config dict.
        overrides: Flat dict of override key/value pairs.

    Returns:
        Tuple of (new SystemInput, new config dict) with overrides applied.
    """
    sys_overrides, cfg_overrides = _split_overrides(overrides)

    new_input = dataclasses.replace(base_input, **sys_overrides) if sys_overrides else base_input
    new_config = copy.deepcopy(base_config)
    new_config.update(cfg_overrides)

    # When load_profile is explicitly overridden, remove per-type map
    # so the override takes effect (mirrors API deps behavior)
    if "load_profile" in cfg_overrides:
        new_config.pop("load_profile_by_type", None)

    return new_input, new_config


def _needs_new_production(overrides: dict[str, Any]) -> bool:
    """Check whether overrides affect production and require a new fetch.

    Args:
        overrides: Flat dict of override key/value pairs.

    Returns:
        True if any key in overrides affects PVGIS output.
    """
    return bool(set(overrides.keys()) & _PRODUCTION_AFFECTING_FIELDS)


async def _run_with_production(
    system_input: SystemInput,
    config: dict[str, Any],
    cached_production: ProductionData | None = None,
) -> ScenarioResult:
    """Run the full pipeline, optionally reusing cached production data.

    Replicates the pipeline from ``main.run_scenario()`` but accepts
    an optional pre-fetched ``ProductionData``.  If provided the PVGIS
    call is skipped.  The Trentino effective_kwp override is still applied.

    Args:
        system_input: System parameters for this scenario.
        config: Merged config dict for this scenario.
        cached_production: Pre-fetched production data to reuse, or None
            to fetch fresh data.

    Returns:
        ScenarioResult with all pipeline stages.
    """
    # Battery cost deduction (same logic as main.py)
    if system_input.battery_kwh > 0:
        from celine.roi.main import estimate_battery_cost

        battery_cost = estimate_battery_cost(system_input.battery_kwh, config)
        pv_capex = max(0.0, system_input.capex - battery_cost)
        logger.info(
            "Battery deduction: %.0f kWh → %.0f EUR → PV CAPEX: %.0f EUR",
            system_input.battery_kwh, battery_cost, pv_capex,
        )
        system_input = dataclasses.replace(system_input, capex=pv_capex)

    if cached_production is not None:
        production_data = cached_production
        logger.info(
            "Reusing cached production data (source: %s, %.0f kWh/year)",
            production_data.source,
            production_data.annual_production_kwh,
        )
    else:
        production_data = await fetch_production(system_input)
        logger.info(
            "Fetched new production: %.0f kWh/year (source: %s)",
            production_data.annual_production_kwh,
            production_data.source,
        )

    # Apply Trentino kWp override if present
    if production_data.effective_kwp is not None:
        if abs(production_data.effective_kwp - system_input.kwp) > 0.5:
            logger.info(
                "Overriding kWp: user=%.1f -> effective=%.1f",
                system_input.kwp,
                production_data.effective_kwp,
            )
        system_input = dataclasses.replace(
            system_input, kwp=production_data.effective_kwp
        )

    # Auto-estimate annual consumption from meter data when not provided
    if (
        system_input.custom_profile_dir is not None
        and system_input.annual_consumption_kwh == 0
    ):
        from celine.roi.config_loader import resolve_config_dir
        from celine.roi.load_profiles import load_meter_data_profile

        meter_path = resolve_config_dir() / "load_profiles" / system_input.custom_profile_dir
        profile_info = load_meter_data_profile(meter_path)
        estimated = profile_info["daily_avg_kwh"] * 365
        logger.info("Auto-estimated annual consumption from meter data: %.0f kWh", estimated)
        system_input = dataclasses.replace(system_input, annual_consumption_kwh=estimated)

    energy = compute_energy(system_input, production_data, config)
    incentives = compute_incentives(system_input, energy, config)
    finance = compute_finance(system_input, incentives, config)
    validation = validate_model(system_input, energy, incentives, finance, config)

    return ScenarioResult(
        system_input=system_input,
        production=production_data,
        energy=energy,
        incentives=incentives,
        finance=finance,
        validation=validation,
    )


# ---------------------------------------------------------------------------
# Summary table formatting
# ---------------------------------------------------------------------------


def _fmt_eur(value: float) -> str:
    """Format a EUR value with thousands separator.

    Args:
        value: Amount in EUR.

    Returns:
        Formatted string like ``12,345`` or ``-1,234``.
    """
    return f"{value:,.0f}"


def _fmt_pct(value: float) -> str:
    """Format a percentage value.

    Args:
        value: Percentage (e.g. 12.3 means 12.3%).

    Returns:
        Formatted string like ``12.3%``.
    """
    return f"{value:.1f}%"


def _fmt_years(value: float) -> str:
    """Format a year value.

    Args:
        value: Number of years.

    Returns:
        Formatted string like ``7.2`` or ``inf``.
    """
    if value == float("inf"):
        return "∞"
    return f"{value:.1f}"


def _delta_eur(base: float, current: float) -> str:
    """Format delta between two EUR values.

    Args:
        base: Base case value.
        current: Current scenario value.

    Returns:
        Delta string like ``+1,234`` or ``-1,234``, or ``—``.
    """
    diff = current - base
    if abs(diff) < 0.5:
        return "—"
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:,.0f}"


def _delta_pct(base: float, current: float) -> str:
    """Format delta between two percentage-point values.

    Args:
        base: Base case percentage.
        current: Current scenario percentage.

    Returns:
        Delta string like ``+2.3pp`` or ``-1.1pp``, or ``—``.
    """
    diff = current - base
    if abs(diff) < 0.05:
        return "—"
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.1f}pp"


def _delta_years(base: float, current: float) -> str:
    """Format delta between two year values.

    Args:
        base: Base case years.
        current: Current scenario years.

    Returns:
        Delta string like ``+1.2`` or ``-0.5``, or ``—``.
    """
    if base == float("inf") or current == float("inf"):
        return "—"
    diff = current - base
    if abs(diff) < 0.05:
        return "—"
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.1f}"


def _extract_kpis(result: ScenarioResult) -> list[tuple[str, float, str]]:
    """Extract KPI rows from a ScenarioResult.

    Args:
        result: Complete scenario result.

    Returns:
        List of (label, raw_value, formatted_string) tuples.
    """
    finance = result.finance
    incentives = result.incentives
    energy = result.energy
    validation = result.validation

    cer_libero_y1 = float(
        incentives.cer_tip_libero[0] + incentives.cer_cacv_libero[0]
    )

    dscr_min: float | None = None
    if finance.dscr is not None and len(finance.dscr) > 0:
        dscr_min = float(np.min(finance.dscr))

    is_valid = len(validation.fails) == 0

    return [
        ("VAN", finance.npv, _fmt_eur(finance.npv)),
        ("TIR", finance.irr * 100, _fmt_pct(finance.irr * 100)),
        ("Payback semplice", finance.payback_simple, _fmt_years(finance.payback_simple)),
        (
            "Payback attualizzato",
            finance.payback_discounted,
            _fmt_years(finance.payback_discounted),
        ),
        (
            "Autoconsumo",
            energy.tasso_autoconsumo * 100,
            _fmt_pct(energy.tasso_autoconsumo * 100),
        ),
        (
            "Produzione anno 1",
            float(incentives.production_degraded[0]),
            _fmt_eur(float(incentives.production_degraded[0])),
        ),
        ("CER libero anno 1", cer_libero_y1, _fmt_eur(cer_libero_y1)),
        (
            "Utile cumulato",
            float(finance.cumulative[-1]),
            _fmt_eur(float(finance.cumulative[-1])),
        ),
        (
            "DSCR min",
            dscr_min if dscr_min is not None else float("nan"),
            f"{dscr_min:.2f}" if dscr_min is not None else "—",
        ),
        ("Valido?", 1.0 if is_valid else 0.0, "✓" if is_valid else "✗"),
    ]


# Delta type per KPI label
_DELTA_TYPES: dict[str, str] = {
    "VAN": "eur",
    "TIR": "pct",
    "Payback semplice": "years",
    "Payback attualizzato": "years",
    "Autoconsumo": "pct",
    "Produzione anno 1": "eur",
    "CER libero anno 1": "eur",
    "Utile cumulato": "eur",
    "DSCR min": "none",
    "Valido?": "none",
}


def _compute_delta(label: str, base_val: float, current_val: float) -> str:
    """Compute formatted delta string for a KPI row.

    Args:
        label: KPI label (used to determine formatting type).
        base_val: Base case raw value.
        current_val: Current scenario raw value.

    Returns:
        Formatted delta string.
    """
    delta_type = _DELTA_TYPES.get(label, "none")
    if delta_type == "eur":
        return _delta_eur(base_val, current_val)
    if delta_type == "pct":
        return _delta_pct(base_val, current_val)
    if delta_type == "years":
        return _delta_years(base_val, current_val)
    return "—"


def _format_summary_table(
    scenarios: dict[str, ScenarioResult],
) -> str:
    """Build a markdown comparison table from scenario results.

    The first scenario is treated as the base case. Subsequent scenarios
    get an additional delta (Δ) column showing differences from base.

    Args:
        scenarios: Ordered dict of scenario name -> ScenarioResult.

    Returns:
        Markdown-formatted table string.
    """
    names = list(scenarios.keys())
    all_kpis: dict[str, list[tuple[str, float, str]]] = {}
    for name, result in scenarios.items():
        all_kpis[name] = _extract_kpis(result)

    base_name = names[0]
    base_kpis = all_kpis[base_name]
    num_kpis = len(base_kpis)

    # Build header
    header_parts = ["| KPI"]
    separator_parts = ["|---"]
    for idx, name in enumerate(names):
        header_parts.append(f"| {name} ")
        separator_parts.append("|---:")
        if idx > 0:
            header_parts.append("| Δ ")
            separator_parts.append("|---:")
    header_parts.append("|")
    separator_parts.append("|")

    header = " ".join(header_parts)
    separator = " ".join(separator_parts)

    # Build rows
    rows: list[str] = []
    for kpi_idx in range(num_kpis):
        label = base_kpis[kpi_idx][0]
        row_parts = [f"| {label} "]
        for scenario_idx, name in enumerate(names):
            kpi_tuple = all_kpis[name][kpi_idx]
            row_parts.append(f"| {kpi_tuple[2]} ")
            if scenario_idx > 0:
                base_val = base_kpis[kpi_idx][1]
                current_val = kpi_tuple[1]
                delta = _compute_delta(label, base_val, current_val)
                row_parts.append(f"| {delta} ")
        row_parts.append("|")
        rows.append(" ".join(row_parts))

    lines = [header, separator] + rows
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def compare_scenarios(
    base_input: SystemInput,
    base_config: dict[str, Any],
    scenarios: dict[str, dict[str, Any]],
) -> ComparisonResult:
    """Run N named scenarios and produce a side-by-side comparison.

    Each scenario is defined by a name and a dict of overrides applied on
    top of ``base_input`` / ``base_config``.  An empty override dict ``{}``
    runs the unmodified base case.

    When a scenario's overrides do not affect production-related fields
    (latitude, longitude, tilt, azimuth, kwp, rooftop_wkt,
    annual_production_kwh), the base case's ``ProductionData`` is reused
    to avoid redundant PVGIS calls.

    Args:
        base_input: Reference system parameters.
        base_config: Merged YAML configuration dict.
        scenarios: Ordered dict of ``{"Scenario Name": {overrides...}}``.

    Returns:
        ComparisonResult with per-scenario results and a markdown
        summary table.

    Raises:
        ValueError: If ``scenarios`` is empty or contains unknown
            override keys.
    """
    if not scenarios:
        raise ValueError("At least one scenario is required.")

    valid_config_keys = frozenset(base_config.keys())

    # Validate all override keys upfront
    for name, overrides in scenarios.items():
        _validate_override_keys(overrides, valid_config_keys)

    results: dict[str, ScenarioResult] = {}
    base_production: ProductionData | None = None

    for name, overrides in scenarios.items():
        logger.info("Running scenario '%s' with %d override(s)", name, len(overrides))

        scenario_input, scenario_config = _apply_overrides(
            base_input, base_config, overrides
        )

        # Decide whether we can reuse cached production
        cached: ProductionData | None = None
        if base_production is not None and not _needs_new_production(overrides):
            cached = base_production

        result = await _run_with_production(scenario_input, scenario_config, cached)
        results[name] = result

        # Cache production from the first scenario (base case)
        if base_production is None:
            base_production = result.production

        logger.info(
            "Scenario '%s' complete: NPV=%.0f EUR, IRR=%.1f%%",
            name,
            result.finance.npv,
            result.finance.irr * 100,
        )

    summary_table = _format_summary_table(results)

    return ComparisonResult(scenarios=results, summary_table=summary_table)
