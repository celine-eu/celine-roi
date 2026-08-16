"""Report formatter for CELINE ROI scenario results.

Generates a human-readable markdown report from pipeline outputs,
including energy summary, CER split, full 25-year cash flow, and validation.
"""

from __future__ import annotations

from typing import Any

from celine.roi.models import ScenarioResult


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
    lines.append("# CELINE ROI — Business Plan Impianto Fotovoltaico")
    lines.append("")
    location = si.location or f"{si.latitude:.4f}N, {si.longitude:.4f}E"
    lines.append(f"**Impianto:** {si.kwp:.1f} kWp | {location}")
    lines.append(
        f"**Investimento:** {si.capex:,.0f} EUR ({si.capex / si.kwp:,.0f} EUR/kWp) — netto IVA"
    )
    lines.append(f"**Regime incentivante:** {si.regime}")
    lines.append(f"**Consumo annuo:** {si.annual_consumption_kwh:,.0f} kWh/anno")
    lines.append(
        f"**Fonte produzione:** {result.production.source}"
    )
    if si.equity_fraction >= 1.0:
        financing_desc = "100% capitale proprio"
    else:
        financing_desc = (
            f"{si.equity_fraction:.0%} capitale proprio"
            f" + {1 - si.equity_fraction:.0%} finanziamento"
            f" ({si.loan_rate:.1%} per {si.loan_duration_years} anni)"
        )
    lines.append(f"**Finanziamento:** {financing_desc}")
    lines.append("")

    # --- Validation failures/warnings ---
    if val.fails:
        lines.append("## ERRORI DI VALIDAZIONE")
        lines.append("")
        for name, msg in val.fails:
            lines.append(f"- **ERRORE** [{name}]: {msg}")
        lines.append("")
        lines.append("> Correggere questi errori prima di utilizzare i risultati.")
        lines.append("")

    if val.warns:
        lines.append("## Avvertenze")
        lines.append("")
        for name, msg in val.warns:
            lines.append(f"- **AVVISO** [{name}]: {msg}")
        lines.append("")

    # --- KPI Summary (top of report for stakeholders) ---
    lines.append("## Sintesi Finanziaria")
    lines.append("")
    lines.append("| Indicatore | Valore |")
    lines.append("|------------|--------|")
    lines.append(f"| **VAN** (tasso sconto {config['wacc']:.1%}) | **{fin.npv:,.0f} EUR** |")
    lines.append(f"| **TIR** | **{fin.irr:.1%}** |")
    lines.append(f"| Payback semplice | {fin.payback_simple:.1f} anni |")
    lines.append(f"| Payback attualizzato | {fin.payback_discounted:.1f} anni |")
    lines.append(f"| Utile cumulato (nominale, 25 anni) | {fin.cumulative[-1]:,.0f} EUR |")
    if fin.dscr is not None:
        min_dscr = float(fin.dscr.min())
        dscr_status = "(OK)" if min_dscr >= 1.25 else "(**sotto 1.25x**)"
        lines.append(f"| DSCR minimo | {min_dscr:.2f}x {dscr_status} |")
    lines.append("")

    # --- Investment Decision ---
    lines.append("### Giudizio")
    lines.append("")
    if val.fails:
        lines.append("**Non valutabile** — correggere gli errori di validazione.")
    elif fin.npv > 0 and fin.irr > config["wacc"]:
        lines.append(
            f"**Investimento consigliato.** VAN positivo ({fin.npv:,.0f} EUR) e "
            f"TIR ({fin.irr:.1%}) superiore al tasso di sconto ({config['wacc']:.1%})."
        )
    elif fin.npv > 0:
        lines.append(
            f"**Marginalmente positivo.** VAN = {fin.npv:,.0f} EUR, "
            f"TIR ({fin.irr:.1%}) vicino al tasso di sconto ({config['wacc']:.1%})."
        )
    else:
        lines.append(
            f"**Investimento non consigliato.** VAN negativo ({fin.npv:,.0f} EUR)."
        )
    lines.append("")

    # --- Energy Summary ---
    lines.append("## Bilancio Energetico (Anno 1)")
    lines.append("")
    lines.append("| Voce | kWh/anno |")
    lines.append("|------|--------:|")
    annual_prod = result.production.annual_production_kwh
    lines.append(f"| Produzione nominale | {annual_prod:,.0f} |")
    lines.append(f"| Produzione post-LID (anno 1) | {inc.production_degraded[0]:,.0f} |")
    lines.append(f"| Autoconsumo | {energy.autoconsumo.sum():,.0f} |")
    lines.append(f"| Tasso autoconsumo | {energy.tasso_autoconsumo:.1%} |")
    lines.append(f"| Immissione in rete | {energy.immissione.sum():,.0f} |")
    lines.append(f"| Energia condivisa CER | {energy.energia_condivisa.sum():,.0f} |")
    lines.append(f"| Prelievo da rete | {energy.prelievo.sum():,.0f} |")
    lines.append("")

    # --- CER Split ---
    cer_libero_ratio = config.get("cer_libero_ratio", 0.55)
    has_cer = "CER" in si.regime
    if has_cer:
        lines.append("## Ripartizione Incentivo CER")
        lines.append("")
        lines.append(
            f"Ai sensi del DM CACER 414/2023, il **{cer_libero_ratio:.0%}** dell'incentivo CER "
            f"e liberamente disponibile al produttore (quota libera). "
            f"Il restante **{1 - cer_libero_ratio:.0%}** e vincolato "
            f"alla redistribuzione ai membri della CER (quota vincolata)."
        )
        lines.append("")
        lines.append("| Voce | Totale (anno 1) | Libero ({:.0%}) | Vincolato ({:.0%}) |".format(
            cer_libero_ratio, 1 - cer_libero_ratio
        ))
        lines.append("|------|----------------:|---------------:|-----------------:|")
        lines.append(
            f"| CER TIP | {inc.cer_tip[0]:,.0f} EUR "
            f"| {inc.cer_tip_libero[0]:,.0f} EUR "
            f"| {inc.cer_tip_vincolato[0]:,.0f} EUR |"
        )
        lines.append(
            f"| CER Cacv | {inc.cer_cacv[0]:,.0f} EUR "
            f"| {inc.cer_cacv_libero[0]:,.0f} EUR "
            f"| {inc.cer_cacv_vincolato[0]:,.0f} EUR |"
        )
        cer_total_y1 = inc.cer_tip[0] + inc.cer_cacv[0]
        cer_libero_y1 = inc.cer_tip_libero[0] + inc.cer_cacv_libero[0]
        cer_vinc_y1 = inc.cer_tip_vincolato[0] + inc.cer_cacv_vincolato[0]
        lines.append(
            f"| **Totale** | **{cer_total_y1:,.0f} EUR** "
            f"| **{cer_libero_y1:,.0f} EUR** "
            f"| **{cer_vinc_y1:,.0f} EUR** |"
        )
        lines.append("")
        lines.append(
            f"> Nel flusso di cassa del produttore entra **solo la quota libera** "
            f"({cer_libero_y1:,.0f} EUR/anno nel primo anno)."
        )
        lines.append("")

    # --- Yearly Revenue Summary (Conto Economico) ---
    lines.append("## Conto Economico Annuale")
    lines.append("")

    useful_life = config["useful_life"]
    general_inflation = config["general_inflation"]
    om_base = config["om_per_kwp"] * si.kwp
    insurance_base = si.capex * config["insurance_rate"]

    lines.append(
        "| Anno | Produz. | Risparmio | RID | CER Lib. | Scudo Fisc. "
        "| IRES+IRAP | O&M+Ass. | Rata Fin. | **CF Netto** | **Cumulato** |"
    )
    lines.append(
        "|-----:|--------:|----------:|----:|---------:|------------:"
        "|----------:|---------:|----------:|-----------:|-----------:|"
    )
    # Year 0
    lines.append(
        f"| 0 | — | — | — | — | — | — | — | — "
        f"| **{fin.cashflows[0]:>10,.0f}** | {fin.cumulative[0]:>10,.0f} |"
    )

    # Loan payment
    import numpy_financial as npf
    debt_principal = si.capex * (1.0 - si.equity_fraction)
    loan_duration = si.loan_duration_years
    if debt_principal > 0 and loan_duration > 0:
        annual_loan = float(-npf.pmt(si.loan_rate, loan_duration, debt_principal))
    else:
        annual_loan = 0.0

    for idx in range(useful_life):
        year = idx + 1
        inflation_factor = (1.0 + general_inflation) ** (year - 1)
        om_ins = (om_base + insurance_base) * inflation_factor
        if year == config["inverter_replacement_year"]:
            from celine.roi.engines.finance import estimate_inverter_cost
            om_ins += estimate_inverter_cost(si.kwp)

        loan_col = annual_loan if year <= loan_duration else 0.0
        cer_lib = inc.cer_tip_libero[idx] + inc.cer_cacv_libero[idx]

        lines.append(
            f"| {year} "
            f"| {inc.production_degraded[idx]:>7,.0f} "
            f"| {inc.risparmio_autoconsumo[idx]:>9,.0f} "
            f"| {inc.rid_revenue[idx]:>3,.0f} "
            f"| {cer_lib:>8,.0f} "
            f"| {inc.tax_shield[idx]:>11,.0f} "
            f"| {inc.ires_irap[idx]:>9,.0f} "
            f"| {om_ins:>8,.0f} "
            f"| {loan_col:>9,.0f} "
            f"| **{fin.cashflows[year]:>10,.0f}** "
            f"| {fin.cumulative[year]:>10,.0f} |"
        )
    lines.append("")

    # --- 25-year totals ---
    lines.append("### Totali 25 anni")
    lines.append("")
    total_risparmio = float(inc.risparmio_autoconsumo.sum())
    total_rid = float(inc.rid_revenue.sum())
    total_cer_lib = float(inc.cer_tip_libero.sum() + inc.cer_cacv_libero.sum())
    total_cer_vinc = float(inc.cer_tip_vincolato.sum() + inc.cer_cacv_vincolato.sum())
    total_tax_shield = float(inc.tax_shield.sum())
    total_ires_irap = float(inc.ires_irap.sum())

    lines.append("| Voce | Totale 25 anni |")
    lines.append("|------|---------------:|")
    lines.append(f"| Risparmio autoconsumo | {total_risparmio:,.0f} EUR |")
    lines.append(f"| Ricavi RID | {total_rid:,.0f} EUR |")
    lines.append(f"| CER incentivo (quota libera) | {total_cer_lib:,.0f} EUR |")
    if has_cer:
        lines.append(
            f"| CER incentivo (quota vincolata, a membri CER) | {total_cer_vinc:,.0f} EUR |"
        )
    lines.append(f"| Scudo fiscale ammortamento | {total_tax_shield:,.0f} EUR |")
    lines.append(f"| IRES + IRAP | -{total_ires_irap:,.0f} EUR |")
    lines.append(f"| **Utile cumulato netto** | **{fin.cumulative[-1]:,.0f} EUR** |")
    lines.append("")

    # --- Key Parameters ---
    lines.append("## Parametri di Calcolo")
    lines.append("")
    lines.append("| Parametro | Valore |")
    lines.append("|-----------|--------|")
    lines.append(f"| Degrado annuo | {config['degradation']*100:.2f}%/anno |")
    lines.append(f"| LID (anno 1) | {config['lid']*100:.1f}% |")
    lines.append(f"| Prezzo energia retail | {config['retail_price']:.2f} EUR/kWh |")
    lines.append(f"| Inflazione energia | {config['energy_inflation']*100:.1f}%/anno |")
    lines.append(f"| Tariffa RID | {config['rid_tariff']:.2f} EUR/kWh |")
    lines.append(
        f"| Tariffa CER TIP | {config['cer_tip']*1000:.1f} EUR/MWh (FISSA nominale, 20 anni) |"
    )
    lines.append(f"| Quota condivisa CER | {config['sharing_ratio']:.0%} |")
    lines.append(
        f"| Ripartizione CER libero/vincolato | "
        f"{cer_libero_ratio:.0%} / {1-cer_libero_ratio:.0%} |"
    )
    lines.append(f"| Tasso sconto (WACC) | {config['wacc']:.1%} |")
    lines.append(
        f"| Ammortamento fiscale | {config['depreciation_coeff']*100:.0f}% "
        f"(anno 1: "
        f"{config['depreciation_coeff']*config['depreciation_first_year_factor']*100:.1f}%) |"
    )
    lines.append(f"| IRES + IRAP | {config['ires']*100:.0f}% + {config['irap']*100:.1f}% |")
    _matching = "Orario (L2, 8760h)" if len(energy.production) > 12 else "Mensile (L1)"
    lines.append(f"| Matching energetico | {_matching} |")
    lines.append("")

    # --- Validation Summary ---
    lines.append("## Controlli di Validazione")
    lines.append("")
    total_checks = len(val.fails) + len(val.warns) + len(val.passes)
    lines.append(
        f"**Risultato:** {len(val.passes)}/{total_checks} superati | "
        f"{len(val.fails)} ERRORI | {len(val.warns)} AVVISI"
    )
    lines.append("")

    return "\n".join(lines)
