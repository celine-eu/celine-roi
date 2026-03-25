# CELINE ROI — Variables & Parameters Reference

All fixed values, configuration parameters, constants, and thresholds used by the tool.

---

## 1. System Defaults (`config/defaults.yaml`)

These are the baseline assumptions when the user doesn't specify custom values. Change these by editing the YAML file — never in code.

| Parameter | Value | What it means | Typical range |
|-----------|-------|---------------|---------------|
| `degradation` | 0.45%/year | How much less energy the panels produce each year due to aging | 0.3–0.6% |
| `lid` | 1.5% | "Light Induced Degradation" — extra production loss in the first year only (new panels stabilizing) | 0–2.5% |
| `performance_ratio` | 0.81 | Ratio of real output vs theoretical max (accounts for heat, wiring, dirt). **Reference only** — already included in PVGIS data | 0.75–0.87 |
| `retail_price` | 0.25 EUR/kWh | What the user pays for grid electricity (from their bill) | 0.18–0.35 |
| `energy_inflation` | 3%/year | How much electricity prices rise each year | 1–5% |
| `general_inflation` | 2%/year | General price inflation (for O&M and insurance costs) | 1–4% |
| `om_per_kwp` | 12 EUR/kWp/year | Operations & maintenance cost per kWp installed (cleaning, monitoring, small repairs) | 8–18 |
| `insurance_rate` | 0.35% of CAPEX/year | Annual insurance cost as a fraction of the initial investment | 0.2–0.5% |
| `wacc` | 5.5% | "Weighted Average Cost of Capital" — the discount rate used to calculate if the investment is worthwhile. Higher = more conservative | 3–9% |
| `useful_life` | 25 years | How long the analysis runs (panel lifetime) | 20–30 |
| `inverter_replacement_year` | Year 12 | When the inverter needs replacing (it wears out before the panels) | Year 10–15 |

**Note:** Inverter replacement *cost* is no longer a config value. It's computed by a power law in `engines/finance.py` — see section 9 below.
| `sharing_ratio` | 55% | What fraction of energy fed to the grid counts as "shared" for the CER incentive. Depends on other CER members' consumption patterns | 40–70% |

## 2. Italian Incentives (`config/incentives.yaml`)

Tariffs and rates set by Italian regulation. Update when new decrees are published.

| Parameter | Value | What it means | Source |
|-----------|-------|---------------|--------|
| `rid_tariff` | 0.07 EUR/kWh | Price at which GSE buys your excess energy (Ritiro Dedicato) | GSE PMZ |
| `cer_tip` | 0.09 EUR/kWh (90 EUR/MWh) | CER incentive tariff. **Fixed for 20 years, never changes with inflation**. Includes +10 EUR/MWh North Italy bonus | Decreto CACER D.M. 414/2023 |
| `cer_cacv` | 0.0085 EUR/kWh (8.5 EUR/MWh) | Additional CER component from ARERA (electricity system charges restitution) | ARERA 727/2022 |
| `cer_duration_years` | 20 years | How long the CER incentive lasts from activation date | Decreto CACER |
| `depreciation_coeff` | 9%/year | Annual tax depreciation rate for roof-mounted PV (classified as "bene mobile") | AdE 46/E/2007, 36/E/2013 |
| `depreciation_first_year_factor` | 50% | First year you only get half the normal depreciation (Italian fiscal rule) | Circular AdE |

## 3. Tax Rates (`config/tax_rates.yaml`)

| Parameter | Value | What it means | Notes |
|-----------|-------|---------------|-------|
| `ires` | 24% | National corporate income tax (applied to RID + CER revenue only, NOT to self-consumption savings) | Fixed by law |
| `irap` | 3.9% | Regional production tax (varies by region: 2.68–4.82%) | Trentino = 3.9% |
| `iva_impianto` | 10% | Reduced VAT on PV system purchase (fully recoverable for businesses) | Fixed by law |

## 4. Solar Distribution Curve

**File:** `celine_roi/pvgis_client.py`

Used only when the user provides annual production manually (no PVGIS call). Distributes the annual total across 12 months following a typical solar pattern for Northern Italy (46°N latitude).

| Month | Fraction | Meaning |
|-------|----------|---------|
| January | 4.9% | Low winter sun |
| February | 5.9% | |
| March | 7.8% | Spring ramp-up |
| April | 9.8% | |
| May | 11.8% | |
| June | **12.7%** | Summer peak |
| July | **12.7%** | Summer peak |
| August | 11.8% | |
| September | 8.8% | |
| October | 6.9% | |
| November | 3.9% | Low winter sun |
| December | **2.9%** | Minimum |

These fractions are normalized to sum to exactly 1.0.

## 5. PVGIS API Settings

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `loss` | 19% | System losses sent to PVGIS (corresponds to ~0.81 performance ratio) |
| API endpoint | `https://re.jrc.ec.europa.eu/api/` | European Commission Joint Research Centre (free, public) |

## 6. Trentino Solar API

| Parameter | Value | Meaning |
|-----------|-------|---------|
| API URL | `https://webgis.provincia.tn.it/wgt/services/solarIrradiance/statistics` | PAT WebGIS solar irradiance service |
| Coverage | Trentino only (lat 45.67–47.09, lon 10.38–11.84) | Returns error outside this area |
| Panel density | 160 W/m² | Assumed by the API when calculating max installable kWp from roof area |
| EPSG auto-detect | Coordinates > 1000 → EPSG:25832 (UTM), else EPSG:4326 (lat/lon) | Automatically chosen based on coordinate magnitude |

## 7. Validation Thresholds

The tool automatically checks your results for common errors. These are the trigger values:

### Regulatory Blockers (FAIL — model invalid)

| Check | Trigger | Why |
|-------|---------|-----|
| SSP regime | Regime = "SSP" | Scambio sul Posto abolished May 2025 |
| CAPEX invalid | CAPEX <= 0 | Can't analyze a free system |
| Zero discount rate | WACC = 0 | Makes NPV meaningless |
| Sharing ratio invalid | < 0 or > 100% | Physically impossible |
| Loan > lifetime | Loan duration > 25 years | Loan outlives the system |

### Parameter Warnings (WARN — results may be unreliable)

| Check | Trigger | Benchmark |
|-------|---------|-----------|
| Low degradation | < 0.3%/year | Industry standard: 0.4–0.5% |
| High degradation | > 1%/year | Unusual, check module warranty |
| Low O&M | < 5 EUR/kWp/year | Benchmark: 8–15 EUR/kWp |
| Low insurance | < 0.2% of CAPEX | Benchmark: 0.25–0.5% |
| High self-consumption | > 80% without battery | Very rare without storage |
| Atypical sharing ratio | < 40% or > 70% | Realistic range: 50–65% |
| Atypical CAPEX/kWp | < 800 or > 1,500 EUR/kWp | 2026 market range |
| No inverter replacement | Year = 0 or cost = 0 | Inverters need replacing around year 10–12 |
| Zero grid export | Immissione = 0 | No RID/CER revenue possible |

### Math Invariants (automatic sanity checks)

| Check | What it verifies |
|-------|-----------------|
| Energy balance | autoconsumo + immissione = production (tolerance: 0.01 kWh) |
| CER within immissione | Shared energy cannot exceed what's fed to grid |
| NPV at 0% | NPV(r=0) must equal the simple sum of all cash flows |
| Depreciation cap | Total depreciation cannot exceed CAPEX |
| Production degrades | Year 25 output must be less than year 1 |

## 8. CLI Defaults

When using the command line, these values are used if you don't specify them:

| Argument | Default | Meaning |
|----------|---------|---------|
| `--kwp` | 0.0 (auto) | System size in kWp. Auto-detected from rooftop polygon when `--rooftop-wkt` is used. Required otherwise. |
| `--tilt` | 30° | Panel tilt angle. Used by PVGIS for monthly production shape. Minimal impact when using Trentino rooftop polygon. |
| `--azimuth` | 0° (south) | Panel compass orientation. Same usage as tilt. Values: 0=south, -90=east, 90=west. |
| `--user-type` | commercial | Consumer category |
| `--regime` | RID_CER | Both RID and CER incentives |
| `--equity-fraction` | 1.0 | Share of CAPEX you pay upfront. 1.0 = 100% equity (no loan). 0.3 = pay 30% upfront, borrow 70%. |
| `--loan-rate` | 0.0 | Annual interest rate on the borrowed portion. Only used if equity-fraction < 1. |
| `--loan-duration` | 0 | Loan repayment period in years. Only used if equity-fraction < 1. |
| `--config-dir` | `config/` | Where to find YAML files |

### How `--equity-fraction` affects the computation

| What changes | equity-fraction = 1.0 (cash) | equity-fraction = 0.3 (70% loan) |
|-------------|------------------------------|-----------------------------------|
| **Year 0 outlay** | -CAPEX (full amount) | -CAPEX * 0.3 (30% of amount) |
| **Yearly costs** | O&M + insurance only | O&M + insurance + loan installment |
| **Loan installment** | None | Fixed annuity for loan-duration years |
| **NPV** | Based on full upfront cost | Based on lower upfront + yearly payments |
| **IRR** | Return on full investment | Return on equity only (leveraged, typically higher) |
| **DSCR** | Not shown | Shown — operating CF / loan payment per year |

Example: 45,000 EUR CAPEX, equity-fraction = 0.3, loan 5% for 15 years:
- Year 0: -13,500 EUR (not -45,000)
- Years 1-15: ~3,040 EUR/year loan payment added to costs
- Years 16-25: no loan payment
- DSCR shown for years 1-15 (banks want >= 1.25x)

## 9. Inverter Replacement Cost (Power Law)

**File:** `celine_roi/engines/finance.py` — `estimate_inverter_cost(kwp)`

The inverter replacement cost is NOT a flat percentage of CAPEX. It's computed with a power law that captures economies of scale (larger systems → lower cost per kWp):

```
cost = 180 × kWp^0.82
```

With a floor of 1,200 EUR and a cap of 120,000 EUR.

| Constant | Value | Meaning |
|----------|-------|---------|
| `BASE` | 180 EUR/kWp | Cost intercept at 1 kWp |
| `ALPHA` | 0.82 | Sub-linear exponent (economies of scale) |
| `FLOOR` | 1,200 EUR | Minimum cost (labor + travel) |
| `CAP` | 120,000 EUR | Maximum (above this → central inverters, different pricing) |

### Reference table

| System size | Estimated cost | EUR/kWp | Market range |
|-------------|---------------|---------|--------------|
| 10 kWp | 1,430 EUR | 143 | 130–160 |
| 30 kWp | 3,600 EUR | 120 | 110–140 |
| 78 kWp | 8,490 EUR | 109 | 95–130 |
| 150 kWp | 14,800 EUR | 99 | 90–120 |
| 300 kWp | 26,200 EUR | 87 | 75–100 |
| 500 kWp | 39,500 EUR | 79 | 70–90 |

Fit on Italian market data ~2025 for string inverters (installed). If you have actual quotes from your installer, you can recalibrate BASE and ALPHA with `scipy.optimize.curve_fit`.
