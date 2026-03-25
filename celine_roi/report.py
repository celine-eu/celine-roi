"""Report formatter for CELINE ROI scenario results.

Generates a human-readable markdown report from pipeline outputs,
including energy summary, full 25-year cash flow, and validation.
"""

from __future__ import annotations

from typing import Any

from celine_roi.models import ScenarioResult


def format_report(
    result: ScenarioResult,
    config: dict[str, Any],
) -> str:
    """Format scenario results as a complete markdown report.

    Args:
        result: Complete scenario output with all intermediate results.
        config: Merged configuration dict.

    Returns:
        Formatted markdown string.
    """
    si = result.system_input
    energy = result.energy
    inc = result.incentives
    fin = result.finance
    val = result.validation

    lines: list[str] = []

    # --- Header ---
    lines.append("# CELINE ROI Scenario Report")
    lines.append("")
    location = si.location or f"{si.latitude:.4f}N, {si.longitude:.4f}E"
    lines.append(f"**System:** {si.kwp:.1f} kWp | {location}")
    lines.append(
        f"**CAPEX:** {si.capex:,.0f} EUR ({si.capex / si.kwp:,.0f} EUR/kWp)"
    )
    lines.append(f"**Regime:** {si.regime}")
    lines.append(
        f"**Production source:** {result.production.source}"
    )
    if si.equity_fraction >= 1.0:
        financing_desc = "100% equity"
    else:
        financing_desc = (
            f"{si.equity_fraction:.0%} equity"
            f" + {1 - si.equity_fraction:.0%} debt"
            f" ({si.loan_rate:.1%} for {si.loan_duration_years}y)"
        )
    lines.append(f"**Financing:** {financing_desc}")
    lines.append("")

    # --- Validation failures/warnings ---
    if val.fails:
        lines.append("## Validation FAILURES")
        lines.append("")
        for name, msg in val.fails:
            lines.append(f"- **FAIL** [{name}]: {msg}")
        lines.append("")
        lines.append("> Fix these issues before using the results below.")
        lines.append("")

    if val.warns:
        lines.append("## Warnings")
        lines.append("")
        for name, msg in val.warns:
            lines.append(f"- **WARN** [{name}]: {msg}")
        lines.append("")

    # --- Energy Summary ---
    lines.append("## Energy Summary (Year 1)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    annual_prod = result.production.annual_production_kwh
    lines.append(f"| Annual production (nameplate) | {annual_prod:,.0f} kWh |")
    lines.append(
        f"| Production after LID (year 1) | {inc.production_degraded[0]:,.0f} kWh |"
    )
    lines.append(
        f"| Self-consumption (autoconsumo) | {energy.autoconsumo.sum():,.0f} kWh |"
    )
    lines.append(
        f"| Self-consumption rate | {energy.tasso_autoconsumo:.1%} |"
    )
    lines.append(f"| Grid feed-in (immissione) | {energy.immissione.sum():,.0f} kWh |")
    lines.append(
        f"| CER shared energy | {energy.energia_condivisa.sum():,.0f} kWh |"
    )
    lines.append(f"| Grid withdrawal (prelievo) | {energy.prelievo.sum():,.0f} kWh |")
    lines.append("")

    # --- Financial KPIs ---
    lines.append("## Financial Summary (25 years)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| NPV (at {config['wacc']:.1%} WACC) | {fin.npv:,.0f} EUR |")
    lines.append(f"| IRR | {fin.irr:.1%} |")
    lines.append(f"| Simple payback | {fin.payback_simple:.1f} years |")
    lines.append(f"| Discounted payback | {fin.payback_discounted:.1f} years |")
    lines.append(f"| Total profit (nominal) | {fin.cumulative[-1]:,.0f} EUR |")
    if fin.dscr is not None:
        min_dscr = float(fin.dscr.min())
        dscr_status = "(OK)" if min_dscr >= 1.25 else "(**below 1.25x**)"
        lines.append(f"| Min DSCR | {min_dscr:.2f}x {dscr_status} |")
    lines.append("")

    # --- Investment Decision ---
    lines.append("## Investment Decision")
    lines.append("")
    if val.fails:
        lines.append("**Cannot evaluate** — fix validation failures first.")
    elif fin.npv > 0 and fin.irr > config["wacc"]:
        lines.append(
            f"**Recommended.** NPV is positive ({fin.npv:,.0f} EUR) and "
            f"IRR ({fin.irr:.1%}) exceeds the discount rate ({config['wacc']:.1%})."
        )
    elif fin.npv > 0:
        lines.append(
            f"**Marginally positive.** NPV is {fin.npv:,.0f} EUR but "
            f"IRR ({fin.irr:.1%}) is close to the discount rate "
            f"({config['wacc']:.1%})."
        )
    else:
        lines.append(
            f"**Not recommended.** NPV is negative ({fin.npv:,.0f} EUR)."
        )
    lines.append("")

    # --- Full Yearly Cash Flow Table ---
    lines.append("## Yearly Cash Flow Detail")
    lines.append("")
    lines.append(
        "| Year | Production | Risparmio | RID | CER TIP | CER Cacv "
        "| Tax Shield | IRES+IRAP | O&M+Ins | Net CF | Cumulative |"
    )
    lines.append(
        "|-----:|-----------:|----------:|----:|--------:|--------:"
        "|-----------:|----------:|--------:|-------:|-----------:|"
    )
    # Year 0
    lines.append(
        f"| 0 | — | — | — | — | — | — | — | — "
        f"| {fin.cashflows[0]:>10,.0f} | {fin.cumulative[0]:>10,.0f} |"
    )

    useful_life = config["useful_life"]
    general_inflation = config["general_inflation"]
    om_base = config["om_per_kwp"] * si.kwp
    insurance_base = si.capex * config["insurance_rate"]

    for idx in range(useful_life):
        year = idx + 1
        inflation_factor = (1.0 + general_inflation) ** (year - 1)
        om_ins = (om_base + insurance_base) * inflation_factor
        if year == config["inverter_replacement_year"]:
            from celine_roi.engines.finance import estimate_inverter_cost

            om_ins += estimate_inverter_cost(si.kwp)

        lines.append(
            f"| {year} "
            f"| {inc.production_degraded[idx]:>10,.0f} "
            f"| {inc.risparmio_autoconsumo[idx]:>9,.0f} "
            f"| {inc.rid_revenue[idx]:>3,.0f} "
            f"| {inc.cer_tip[idx]:>7,.0f} "
            f"| {inc.cer_cacv[idx]:>7,.0f} "
            f"| {inc.tax_shield[idx]:>10,.0f} "
            f"| {inc.ires_irap[idx]:>9,.0f} "
            f"| {om_ins:>7,.0f} "
            f"| {fin.cashflows[year]:>6,.0f} "
            f"| {fin.cumulative[year]:>10,.0f} |"
        )
    lines.append("")

    # --- Key Parameters ---
    lines.append("## Key Parameters")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Degradation | {config['degradation']*100:.2f}%/year |")
    lines.append(f"| LID (year 1) | {config['lid']*100:.1f}% |")
    lines.append(f"| Retail price | {config['retail_price']:.2f} EUR/kWh |")
    lines.append(f"| Energy inflation | {config['energy_inflation']*100:.1f}%/year |")
    lines.append(f"| RID tariff | {config['rid_tariff']:.2f} EUR/kWh |")
    lines.append(
        f"| CER TIP tariff | {config['cer_tip']*1000:.1f} EUR/MWh (FIXED) |"
    )
    lines.append(f"| Sharing ratio | {config['sharing_ratio']:.0%} |")
    lines.append(f"| WACC | {config['wacc']:.1%} |")
    lines.append(
        f"| Depreciation | {config['depreciation_coeff']*100:.0f}% "
        f"(year 1: {config['depreciation_coeff']*config['depreciation_first_year_factor']*100:.1f}%) |"
    )
    lines.append(f"| IRES + IRAP | {config['ires']*100:.0f}% + {config['irap']*100:.1f}% |")
    lines.append("")

    # --- Validation Summary ---
    lines.append("## Validation Checks")
    lines.append("")
    total = len(val.fails) + len(val.warns) + len(val.passes)
    lines.append(
        f"**Score:** {len(val.passes)}/{total} passed | "
        f"{len(val.fails)} FAIL | {len(val.warns)} WARN"
    )
    lines.append("")

    return "\n".join(lines)
