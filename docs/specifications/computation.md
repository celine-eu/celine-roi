# Specifications — the computation

The pipeline, and the four engines it chains. See [index.md](index.md) for what these
requirements are and are not.

The pipeline order is described in [`../architecture.md`](../architecture.md) and is not
restated here.

---

## REQ-01xx — the pipeline and energy matching

### REQ-0101 — the pipeline returns a complete result

`run_scenario` executes production → energy → incentives → finance → validation and
returns a `ScenarioResult` carrying every stage's output. A caller never has to run a
stage itself to obtain an intermediate figure.

*Verified by* `tests/test_main.py::TestRunScenario`

### REQ-0102 — energy balance

For every period, self-consumed energy plus exported energy equals production:

```text
autoconsumo + immissione == production
```

This holds for monthly matching (12 periods) and hourly matching (8760) alike. It is
checked to within 0.01 kWh over the year, and is also asserted inside the pipeline
itself — a violation raises rather than returning a wrong answer.

*Verified by* `tests/test_energy.py::TestComputeEnergy`,
`tests/test_energy_hourly.py::TestHourlyEnergyMatching`,
`tests/test_validation.py::TestValidateModelInvariants`

### REQ-0103 — consumption balance

For every period, self-consumed energy plus energy drawn from the grid equals
consumption:

```text
autoconsumo + prelievo == consumption
```

*Verified by* `tests/test_energy.py::TestComputeEnergy`,
`tests/test_energy_hourly.py::TestHourlyEnergyMatching`

### REQ-0104 — matching is physically bounded

Self-consumption never exceeds production and never exceeds consumption; exported energy
is never negative; the self-consumption ratio lies in `[0, 1]`.

These are separate from REQ-0102 on purpose: the balance can hold while both sides are
nonsense.

*Verified by* `tests/test_energy.py::TestComputeEnergy`,
`tests/test_energy_hourly.py::TestHourlyEnergyMatching`

### REQ-0105 — CER shared energy derives from exported energy

Shared energy is the exported energy scaled by the configured sharing ratio, and is
therefore never greater than what was exported. A separate virtual-consumption rate
reduces it further, modelling the share a small CER can actually absorb; unset, it
behaves as it did before the parameter existed.

*Verified by* `tests/test_energy.py::TestComputeEnergy`

### REQ-0106 — hourly matching where possible, monthly where not

When production carries an 8760-element hourly series, matching runs hourly and every
output array is 8760 elements. With no hourly series it falls back to 12-element monthly
matching, and the monthly figures are unchanged by the presence of the fallback.

The distinction matters: monthly matching averages away the daily mismatch between a
solar peak and an evening load, and overstates self-consumption as a result.

*Verified by* `tests/test_energy_hourly.py::TestHourlyFallbackToMonthly`

### REQ-0107 — the load profile follows the user type, unless overridden

Each `user_type` maps to a load profile, and the profiles differ in the way the domain
requires: commercial and industrial consumers self-consume more of the same production
than a residential one, because their load is daytime-weighted. An explicit
`load_profile` override wins over the mapping.

*Verified by* `tests/test_energy_hourly.py::TestProfileRoutingByUserType`

### REQ-0108 — a heat pump is matched, not appended

`heat_pump_kwh_annual` adds to total consumption and is blended into the load profile
before matching, so it raises self-consumption rather than simply raising the bill. The
energy balance holds with it present.

*Verified by* `tests/test_energy_hourly.py::TestHeatPumpKwhAnnual`,
`tests/test_load_profiles.py::TestBuildHourlyConsumptionWithHeatPump`

### REQ-0109 — the degenerate cases produce a result, not an exception

Zero consumption and consumption far above production both compute. They are the two
ends a caller reaches by accident.

*Verified by* `tests/test_energy.py::TestComputeEnergyEdgeCases`

### REQ-0110 — self-consumption lands in a plausible band

For the reference residential, oversized and heat-pump cases, the resulting
self-consumption rate is within the band published for comparable Italian systems.

This is the one requirement here that is a sanity check rather than an invariant. It
exists because every arithmetic invariant above can hold while the model is calibrated
wrongly.

*Verified by* `tests/test_energy_validation.py::TestResidentialBenchmarks`

### REQ-0111 — validation separates blockers from warnings

`validate_model` returns three lists: regulatory **fails** that make the model invalid,
parameter **warns** that make it unreliable, and **passes**. The reference case produces
no fails and at least one pass.

The distinction is what lets the API return 200 with `is_valid: false` rather than
refusing the request: an unviable scenario is a result, not an error.

Regulatory blockers include the SSP regime (withdrawn, and modelling it would produce a
number for a scheme nobody can enter), a zero CAPEX, and a zero discount rate.

*Verified by* `tests/test_validation.py::TestValidateModelPasses`,
`tests/test_validation.py::TestValidateModelRegulatory`,
`tests/test_validation.py::TestValidateModelWarnings`

### REQ-0112 — implausible heat pump sizing warns

A heat pump load larger than the base consumption warns rather than failing; it is
unusual, not impossible.

*Verified by* `tests/test_validation.py::TestHeatPumpValidation`

---

## REQ-05xx — incentives and Italian regulation

The **values** these requirements operate on are in `config/*.yaml` and change by
legislation. What is specified here is the shape of each calculation. See
[`../variables-reference.md`](../variables-reference.md).

### REQ-0501 — every incentive series spans the configured useful life

All arrays returned by the incentive engine are indexed by year and have exactly
`useful_life` entries.

*Verified by* `tests/test_incentives.py::TestComputeIncentivesYear1`

### REQ-0502 — production degrades on a two-part schedule

Year 1 takes a one-off light-induced degradation loss, and every year after that
compounds the annual degradation rate:

```text
production(y) = annual × (1 − lid_loss) × (1 − degradation_rate)^(y−1)
```

Production is therefore strictly decreasing over the lifetime.

*Verified by* `tests/test_incentives.py::TestComputeIncentivesDegradation`

### REQ-0503 — CER incentives run 20 years, and TIP is fixed nominal

Both CER components are zero from year 21. Within the 20 years, the **TIP tariff is
fixed in nominal terms** — it is not escalated by energy inflation, while the Cacv
component is. An implementation that inflated TIP would overstate the return of every
CER scenario, and would look correct in year 1.

*Verified by* `tests/test_incentives.py::TestComputeIncentivesCER20Year`

### REQ-0504 — RID revenue is earned on exported energy

Feed-in revenue is the exported energy at the RID tariff, escalated with energy prices.

*Verified by* `tests/test_incentives.py::TestComputeIncentivesYear1`

### REQ-0505 — self-consumption savings are not taxed

IRES and IRAP are computed on RID and CER revenue only. Avoided cost is not income, and
taxing it would understate every scenario.

*Verified by* `tests/test_incentives.py::TestComputeIncentivesDegradation`

### REQ-0506 — depreciation is capped at CAPEX, and is for businesses only

The depreciation schedule sums to exactly the CAPEX, applies a reduced factor
(`depreciation_first_year_factor`) in the first year and the full rate thereafter, and is
zero once complete. **Residential users get none** — they get the IRPEF deduction
instead, and never both.

*Verified by* `tests/test_incentives.py::TestComputeIncentivesDepreciation`,
`tests/test_incentives.py::TestDepreciationGating`,
`tests/test_validation.py::TestValidateModelInvariants`

### REQ-0507 — the IRPEF deduction is restricted, capped, and spread

The deduction applies only to residential systems of 20 kWp or less. Its base is the
CAPEX capped at €96 000, optionally grossed up by IVA, and it is paid in equal
instalments over 10 years. The rate depends on whether the system serves a primary
residence.

*Verified by* `tests/test_incentives.py::TestDetrazioneIrpef`

### REQ-0508 — the deduction's parameters are per-request

A caller may disable the deduction, override its rate, its number of instalments, and
whether IVA is included in the base. These are the parameters that change with the
budget law, so a caller modelling next year must not have to wait for a deployment.

*Verified by* `tests/test_incentives.py::TestDetrazioneConfigurable`

### REQ-0509 — the CER virtual consumption rate applies across the lifetime

Where set, it reduces shared energy in every year, not only year 1.

*Verified by* `tests/test_incentives.py::TestCerVirtualRateMultiYear`

---

## REQ-06xx — finance

### REQ-0601 — year 0 is the equity outlay alone

The year-0 cashflow is `−CAPEX × equity_fraction`. Debt-funded CAPEX does not appear as
an outflow at year 0; it appears as debt service in the years that follow.

*Verified by* `tests/test_finance.py::TestComputeFinance`,
`tests/test_finance.py::TestFinanceWithLoan`

### REQ-0602 — NPV at a zero discount rate is the sum of the cashflows

The arithmetic check that catches an off-by-one in the discounting exponent, which no
amount of plausible-looking output would reveal.

*Verified by* `tests/test_finance.py::TestFinanceInvariants`

### REQ-0603 — discounted payback is never shorter than simple payback

*Verified by* `tests/test_finance.py::TestComputeFinance`

### REQ-0604 — DSCR exists only where there is debt

At 100% equity the debt service coverage ratio is `None`, not zero and not a series of
infinities. A financed scenario produces one.

*Verified by* `tests/test_finance.py::TestComputeFinance`,
`tests/test_finance.py::TestFinanceWithLoan`

### REQ-0605 — the inverter is replaced during the lifetime

A replacement cost falls in year 12, so that year's cashflow is below the year before it.
Omitting it overstates the return of every scenario by roughly one inverter.

*Verified by* `tests/test_finance.py::TestFinanceInvariants`

### REQ-0606 — the IRPEF deduction reaches the cashflows

A residential scenario's cashflows include the deduction; a commercial scenario's are
unaffected by it. This is the join between REQ-0507 and the finance engine, and it is
specified separately because the two engines can each be right while the hand-off is not.

*Verified by* `tests/test_finance.py::TestFinanceWithDetrazione`

---

## REQ-07xx — CAPEX estimation

### REQ-0701 — panel count follows rooftop area, bounded by the kWp limit

The number of panels a rooftop supports derives from its usable area and the panel
specification, and is capped by the configured maximum system size. Zero area yields zero
panels.

*Verified by* `tests/test_capex_estimator.py::TestMaxPanelsForArea`

### REQ-0702 — cost per Wp falls with system size, down to a floor

Larger systems cost less per Wp, following the configured cost curve, and never fall
below the configured floor. The floor is what stops extrapolation from producing a free
installation.

*Verified by* `tests/test_capex_estimator.py::TestEstimateCapex`

### REQ-0703 — panel counts outside the supported range are rejected

Too few and too many both raise rather than extrapolating off the end of the cost curve.

*Verified by* `tests/test_capex_estimator.py::TestEstimateCapex`

### REQ-0704 — the panel and cost specifications load from configuration

Panel specifications and the cost curve are configuration, not constants in the
estimator.

*Verified by* `tests/test_capex_estimator.py::TestLoadPanelSpecs`

---

## REQ-08xx — configuration and load profiles

### REQ-0801 — configuration merges every YAML file in the directory

`load_config` merges `defaults.yaml`, `incentives.yaml`, `tax_rates.yaml` and
`panel_specs.yaml` into one flat dict, whose values are those in the files. A missing
config directory raises rather than falling back to built-in defaults — a service
silently running on defaults is worse than one that refuses to start.

*Verified by* `tests/test_config_loader.py::TestLoadConfig`

### REQ-0802 — load profiles are normalised, and validated on load

An hourly coefficient set sums to 1 and has 24 entries; monthly weights sum to 1. A
profile missing either, or carrying the wrong number of hourly coefficients, raises at
load time rather than producing a quietly rescaled result.

*Verified by* `tests/test_load_profiles.py::TestLoadProfileConfig`,
`tests/test_load_profiles.py::TestLoadProfileConfigErrors`

### REQ-0803 — hourly consumption preserves the annual total

Expanding an annual consumption figure to 8760 hours reproduces that annual total, emits
no negative values, and distributes across months according to the profile's weights.
Negative consumption is rejected.

*Verified by* `tests/test_load_profiles.py::TestBuildHourlyConsumption`

### REQ-0804 — a caller may supply its own load profile

A caller may pass 24 mean hourly values directly, or name a directory of daily meter
readings in the C2G / e-distribuzione export format, instead of using a named profile.
Manual hourly values take priority over a meter directory. A meter export that cannot be
parsed is skipped rather than failing the whole folder.

The meter-data tests build their own export folder. They previously pointed at one
customer's real readings, which existed on a single machine — so every one of them
skipped everywhere and this requirement had no running verification at all.

*Verified by* `tests/test_custom_profile.py::TestManualProfile`,
`tests/test_custom_profile.py::TestMeterDataProfile`,
`tests/test_custom_profile.py::TestEnergyCustomProfile`
