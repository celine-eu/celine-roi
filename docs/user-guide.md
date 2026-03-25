# CELINE ROI — User Guide

A practical guide for non-technical users. No programming knowledge required.

---

## What This Tool Does

You're considering installing solar panels. This tool answers one question: **is it a good investment?**

You provide basic information about the system (location, cost, your electricity consumption), and it calculates:

- How much money you'll save and earn over 25 years
- How quickly you'll recover your investment
- Whether the numbers make sense given Italian tax rules and incentives

It accounts for things that simple calculators miss: panel degradation over time, Italian-specific tax treatment, CER incentives, depreciation, inflation, and inverter replacement.

---

## What You Need to Provide (Inputs)

### Required

| Input | Example | How to get it |
|-------|---------|---------------|
| **Location (lat/lon)** | 45.93, 11.27 | Google Maps: right-click on the site → "What's here?" → copy the coordinates |
| **Total cost (CAPEX)** | 45,000 EUR | Your installer's quote, the "netto IVA" amount (before VAT). See "How to estimate CAPEX" below |
| **Annual electricity consumption** | 40,000 kWh | Sum of 12 months from your electricity bills. Look for "Consumo totale" or "kWh prelevati" on each bill |

### Optional (have good defaults)

| Input | Default | When to change it |
|-------|---------|-------------------|
| System size (kWp) | Auto-detected from rooftop polygon, or required if no polygon | Only needed if you're NOT using `--rooftop-wkt` |
| Rooftop polygon (WKT) | None | **Recommended for Trentino sites** — gives the most accurate results. See below |
| Panel tilt | 30° | Only used for PVGIS monthly shape. If you have the Trentino rooftop polygon, this has minimal impact |
| Panel orientation | South (0°) | Same as tilt — mainly affects PVGIS. Values: 0=south, -90=east, 90=west |
| Regime | RID + CER | Change to "RID" if you're not joining a CER community |
| Financing | 100% equity | If taking a loan, specify equity share, rate, and duration. See below |
| Annual production | Auto (from PVGIS/Trentino) | Only if you have a more accurate estimate from your installer |

### How to estimate CAPEX

The CAPEX is the total cost of the PV system **before VAT (IVA)**. It includes panels, inverter, mounting, wiring, installation labor, permits, and grid connection.

Typical 2026 prices in Italy:

| System size | Price range (net of IVA) | EUR/kWp |
|-------------|-------------------------|---------|
| 3-6 kWp (residential) | 4,000–8,000 EUR | 1,100–1,400 |
| 10-20 kWp (small commercial) | 9,000–22,000 EUR | 900–1,100 |
| 20-50 kWp (medium commercial) | 18,000–45,000 EUR | 850–1,000 |
| 50-100 kWp (industrial) | 40,000–85,000 EUR | 800–950 |

Ask your installer for a quote. The number you need is the "Importo imponibile" (taxable amount) on the preventivo, NOT the final total with IVA.

### How to use the rooftop polygon

For **Trentino sites**, you can get a precise rooftop polygon from the provincial WebGIS:

1. Go to the [Trentino Solar Map](https://webgis.provincia.tn.it/wgt/?topic=19)
2. Find your building
3. Click on the rooftop — the tool will return a polygon with coordinates
4. Copy the polygon in WKT format: `POLYGON((x1 y1, x2 y2, ...))`
5. Pass it with `--rooftop-wkt "POLYGON((...))"`

When you use a rooftop polygon:
- The **system size (kWp)** is automatically calculated from the roof area (you don't need to specify `--kwp`)
- The **annual production** uses LIDAR data that accounts for mountain shadows and nearby buildings — much more accurate than PVGIS for Alpine valleys
- The **tilt and azimuth** have minimal impact (only used for the monthly shape from PVGIS)

### How equity fraction and financing work

By default, the tool assumes you pay 100% upfront (equity). If you're taking a loan:

- `--equity-fraction 0.3` means you pay 30% upfront and borrow 70%
- `--loan-rate 0.05` means 5% annual interest on the loan
- `--loan-duration 15` means 15-year loan

**What changes with financing:**
- **Year 0 outlay drops**: You only put down 30% of CAPEX instead of 100%
- **Yearly costs increase**: You pay loan installments (principal + interest) for the loan duration
- **NPV may change**: Lower upfront cost but higher yearly costs — depends on the interest rate vs WACC
- **DSCR appears**: The report shows whether your yearly cash flow covers the loan payment (banks want DSCR >= 1.25x)

Example: 45,000 EUR system, 30% equity, 5% rate, 15 years:
- Year 0: you pay 13,500 EUR (not 45,000)
- Years 1-15: you pay ~3,040 EUR/year loan installment
- Years 16-25: no loan payment (paid off)

---

## Where Location is Used

Your latitude/longitude coordinates are used in two places:

1. **PVGIS API** — calls the European Commission's solar database to get how much energy your panels will produce each month at your specific location, accounting for local climate and sun angle
2. **Trentino check** — if your coordinates are in Trentino (lat 45.67–47.09, lon 10.38–11.84) AND you provide a rooftop polygon, the tool uses the provincial LIDAR-based solar data instead of PVGIS for the annual total (more accurate in mountains)

If you use `--production` to manually specify annual production, the location is not used for production — but it's still in the report for reference.

---

## Where Tilt and Azimuth Are Used

These parameters are passed to the **PVGIS API** to simulate how your panels perform:

- **Tilt** = angle of the panels relative to horizontal (0° = flat on the ground, 90° = vertical wall). Most rooftops are 15–35°.
- **Azimuth** = compass direction the panels face (0° = due south, -90° = east, 90° = west).

**When do they matter?**
- If using PVGIS only (no rooftop polygon): **they directly affect the production estimate**. Wrong values → wrong results.
- If using the Trentino rooftop polygon: **minimal impact** — they only affect the monthly distribution shape (how production is split across months). The annual total comes from LIDAR, which already knows your roof angle.

If you don't know your roof tilt, 30° is a reasonable default for Italy. If you don't know the orientation, 0° (south) is the most common.

---

## How to Run It

Open a terminal in the project directory and run:

```bash
python -m celine_roi \
  --lat 45.9333 --lon 11.2667 \
  --capex 45000 \
  --consumption 40000 \
  --rooftop-wkt "POLYGON((667942.60 5087070.19, ...))" \
  --location "My Site"
```

Without a rooftop polygon (you must specify kWp):

```bash
python -m celine_roi \
  --kwp 45 \
  --lat 45.9333 --lon 11.2667 \
  --capex 45000 \
  --consumption 40000
```

To save the report to a file:

```bash
python -m celine_roi \
  --kwp 45 --lat 45.9333 --lon 11.2667 \
  --capex 45000 --consumption 40000 \
  --output report.md
```

With financing (70% loan):

```bash
python -m celine_roi \
  --kwp 45 --lat 45.9333 --lon 11.2667 \
  --capex 45000 --consumption 40000 \
  --equity-fraction 0.3 --loan-rate 0.05 --loan-duration 15
```

---

## How to Read the Output

The report has 7 sections. Here's what each one tells you.

### 1. Header

```
System: 31.4 kWp | Lavarone, Trentino
CAPEX: 31,400 EUR (1,000 EUR/kWp)
Regime: RID_CER
Production source: trentino+pvgis
Financing: 100% equity
```

Summary of your inputs. **Check that kWp matches your expectation** — if you used a rooftop polygon, the kWp is calculated from the roof area (area * 160 W/m²). The EUR/kWp figure tells you if the system price is in the normal market range (800–1,500 EUR/kWp in 2026).

The **production source** tells you where the energy estimate came from:
- `trentino+pvgis` — LIDAR-based annual total + PVGIS monthly shape (best for Trentino)
- `pvgis` — PVGIS satellite data only
- `synthetic` — you provided annual production manually, distributed with a standard solar curve

### 2. Warnings (if any)

```
WARN [high_autoconsumo]: Self-consumption 81.8% — rare without battery
```

The tool flags anything unusual. Warnings don't invalidate the results but suggest you double-check an assumption. Common warnings:

- **High self-consumption**: Your system is small relative to consumption — you use almost everything you produce. This is actually fine, but the tool flags it because >80% without battery storage is uncommon.
- **Low degradation**: You changed this parameter to be more optimistic than industry benchmarks.
- **Atypical CAPEX/kWp**: Your system cost is unusually low or high — verify the installer quote.

If you see a **FAIL** instead of a WARN, the results cannot be trusted until you fix the issue.

### 3. Energy Summary (Year 1)

```
Annual production (nameplate)       29,600 kWh
Production after LID (year 1)       29,156 kWh
Self-consumption (autoconsumo)      24,208 kWh
Self-consumption rate               81.8%
Grid feed-in (immissione)            5,393 kWh
CER shared energy                    2,966 kWh
Grid withdrawal (prelievo)          15,792 kWh
```

This shows how your energy flows in year 1:

- **Nameplate production**: What the panels produce in a typical year (before any degradation)
- **After LID**: Year 1 has a one-time ~1.5% loss as new panels stabilize
- **Self-consumption (autoconsumo)**: Energy you use directly instead of buying from the grid. **This is where most of the value comes from** — every kWh self-consumed saves you the full retail price (~0.25 EUR/kWh)
- **Grid feed-in (immissione)**: Excess energy sold back to the grid at a lower price (~0.07 EUR/kWh via RID)
- **CER shared energy**: The portion of your excess that qualifies for the CER incentive (55% of immissione by default). Earns an additional ~0.09 EUR/kWh
- **Grid withdrawal (prelievo)**: Energy you still need to buy from the grid (evenings, cloudy days)

**Key insight**: Self-consumed energy is worth ~3.5x more than exported energy. A higher self-consumption rate = more value.

### 4. Financial Summary

```
NPV (at 5.5% WACC)      76,251 EUR
IRR                      22.9%
Simple payback           4.6 years
Discounted payback       5.4 years
Total profit (nominal)   181,119 EUR
```

The key numbers:

- **NPV (Net Present Value)**: The total value of the investment in today's euros, accounting for the time value of money. **If NPV > 0, the investment creates value.** Think of it as "how much richer are you in today's money after 25 years?"
- **IRR (Internal Rate of Return)**: The effective annual return. Compare it to alternative investments: 22.9% is excellent — most financial investments return 5–10%.
- **Simple payback**: How many years until cumulative savings cover the initial cost. 4.6 years means you "get your money back" in about 4.5 years, then enjoy 20+ years of profit.
- **Discounted payback**: Same, but accounts for the fact that money tomorrow is worth less than today. Always longer than simple payback.
- **Total profit**: Simple sum of all cash flows over 25 years.

**If financed (with a loan)**, you'll also see:
- **Min DSCR**: Debt Service Coverage Ratio. Banks want >= 1.25x. Below that, the project may not get financing.

### 5. Investment Decision

```
Recommended. NPV is positive (76,251 EUR) and IRR (22.9%) exceeds the discount rate (5.5%).
```

A clear yes/no recommendation:

| Verdict | Meaning |
|---------|---------|
| **Recommended** | NPV positive AND IRR above your target return — go for it |
| **Marginally positive** | NPV positive but IRR is close to the threshold — proceed with caution |
| **Not recommended** | NPV negative — you'd be better off investing elsewhere |
| **Cannot evaluate** | There are validation failures — fix them first |

### 6. Yearly Cash Flow Detail

The full 25-year table:

| Column | What it means |
|--------|---------------|
| **Year** | Year of operation (0 = purchase day) |
| **Production** | kWh produced (decreases ~0.45%/year due to aging) |
| **Risparmio** | Savings from self-consuming instead of buying from grid (grows with energy inflation) |
| **RID** | Revenue from selling excess via Ritiro Dedicato |
| **CER TIP** | CER incentive (fixed tariff, does NOT grow with inflation, **stops at year 20**) |
| **CER Cacv** | Additional CER component (grows with inflation, **stops at year 20**) |
| **Tax Shield** | Tax savings from depreciating the system (~12 years, then drops to zero) |
| **IRES+IRAP** | Taxes on RID + CER revenue. **Self-consumption is NOT taxed** |
| **O&M+Ins** | Maintenance + insurance (grows with inflation). Year 12 includes inverter replacement |
| **Net CF** | Everything in minus everything out for that year |
| **Cumulative** | Running total — **when this turns positive, you've recovered your investment** |

**Things to notice:**
- Year 0 is negative (your investment)
- CER income drops to zero after year 20
- Tax Shield drops to zero after year 12 (fully depreciated)
- Year 12 has a cash flow dip (inverter replacement)
- Risparmio grows every year (electricity prices rise)
- Cumulative turns positive around year 4-5 (payback)

### 7. Key Parameters

Lists all assumptions used. Check these match your situation. If a default doesn't apply (e.g., your region's IRAP differs), edit the YAML config files in `config/`.

---

## Understanding the Revenue Streams

Your PV system generates money in 4 different ways:

```
1. SELF-CONSUMPTION SAVINGS (biggest, ~70-80% of value)
   You use the energy yourself instead of buying it.
   Worth: full retail price (~0.25 EUR/kWh)
   Tax: NOT taxed (it's an avoided cost, not income)

2. RID — RITIRO DEDICATO (~10-15% of value)
   GSE buys your excess energy at wholesale price.
   Worth: ~0.07 EUR/kWh (variable)
   Tax: IRES (24%) + IRAP (3.9%) = 27.9%

3. CER INCENTIVE (~5-10% of value)
   If you join a Renewable Energy Community, you earn a
   bonus on shared energy. Fixed tariff for 20 years.
   Worth: ~0.09 EUR/kWh (fixed, never changes)
   Tax: IRES (24%) + IRAP (3.9%) = 27.9%

4. TAX DEPRECIATION (~5% of value)
   You deduct the PV cost from your business taxes over ~12 years.
   Worth: 24% of annual depreciation amount
   Lasts: ~12 years (9% rate, 50% in year 1)
```

**Important**: SSP (Scambio sul Posto) was **abolished in May 2025**. This tool does not include it. Any analysis that mentions SSP for new systems is outdated.

---

## Frequently Asked Questions

**Q: Why is the self-consumption rate so important?**
Every kWh you self-consume saves you ~0.25 EUR (retail price). Every kWh you export earns only ~0.07 EUR (RID) + ~0.05 EUR (CER share). Self-consumption is worth 2–3x more. Size your system relative to your consumption.

**Q: Why does the CER income stop at year 20?**
The Decreto CACER (D.M. 414/2023) grants the incentive for exactly 20 years. After that, you still earn RID on exported energy, but the CER bonus ends.

**Q: Why is the CER tariff "fixed" while everything else inflates?**
By decree. The 90 EUR/MWh tariff is nominal and constant. Its real value erodes with inflation — at 3%/year, it's worth ~45% less in real terms by year 20.

**Q: What's the difference between the Trentino API and PVGIS?**
PVGIS uses satellite data and assumes a flat horizon. The Trentino API uses LIDAR scans of actual terrain and buildings, so it accounts for mountain shadows. For Alpine valleys, PVGIS can overestimate production by 10-30%.

**Q: Can I change the default parameters?**
Yes. Edit the YAML files in `config/`. For example, if your regional IRAP is 4.82%, change `irap: 0.0482` in `config/tax_rates.yaml`. No code changes needed.

**Q: What does the WACC really mean?**
It's your "minimum acceptable return." If you could earn 5.5% by investing your money elsewhere, then WACC = 5.5%. The PV investment only makes sense if its return (IRR) exceeds this. A higher WACC = you're more demanding = fewer projects look attractive.

**Q: What if I don't know my kWp?**
If you're in Trentino and have a rooftop polygon, you don't need to specify kWp — the tool calculates it from the roof area. Otherwise, ask your installer. As a rough estimate: 1 kWp needs ~5-6 m² of roof area.
