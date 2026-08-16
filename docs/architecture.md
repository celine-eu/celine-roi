# Architecture

`celine-roi` is a financial decision engine for Italian photovoltaic installations. Given
system specifications — kWp, location, CAPEX, consumption — it returns 25-year financial
projections under Italian incentive regimes.

It is a **pure computation service**: it owns no data schema shared with other components,
calls no other CELINE service, and stores only its own results.

## The pipeline is a strict chain

Executed in `run_scenario`, in `src/celine/roi/main.py`:

```text
SystemInput
  → fetch_production      PVGIS, or Trentino Solar LIDAR
  → compute_energy        hourly and monthly production vs consumption
  → compute_incentives    25-year RID, CER TIP/Cacv, IRPEF deduction, depreciation
  → compute_finance       NPV, IRR, payback, DSCR, cumulative cashflows
  → validate_model        regulatory and parameter sanity checks
  → ScenarioResult
```

**The order is load-bearing.** Each stage consumes the previous stage's output, so a phase
cannot be reordered or skipped — and a change to what one stage returns is a change to
every stage after it.

## Every phase is also an endpoint

Each stage is exposed twice:

| Endpoint | Runs |
|---|---|
| `/api/v1/{phase}` | that phase alone, with its inputs supplied directly |
| `/api/v1/scenario` | the whole chain |
| `/api/v1/compare` | several scenarios side by side, via `src/celine/roi/scenarios/comparator.py` |

That duality is the thing to remember when changing a phase: a signature change affects
both the chain *and* a public endpoint, and the endpoint is the one nobody re-runs while
testing the chain.

## Where the layers are

| Layer | Holds |
|---|---|
| `models.py` | the domain: frozen dataclasses carrying numpy arrays. No database, no serialization |
| `engines/` | the computation — `energy.py`, `incentives.py`, `finance.py` |
| `src/celine/roi/validation/warnings.py` | regulatory and parameter sanity checks |
| `api/` | the boundary: FastAPI app, request/response schemas, dependencies, one file per route |
| `config/*.yaml` | the parameters, merged flat at startup by `config_loader.py` |

The source tree itself is the reference for what exists; this table is about what each
layer is *for*. What must not cross between them is in the companion's knowledge.

## External calls

`pvgis_client.py` is the **only** part of this service that reaches the network: the EU
PVGIS API, and optionally the Trentino Solar LIDAR API. Both can be bypassed —
`annual_production_kwh` supplies a synthetic distribution, `rooftop_wkt` selects the
Trentino path.

## The Italian regulatory domain

Every financial figure is Italian-specific: IRPEF deduction at 50% or 36% depending on
primary residence, IRES and IRAP taxation, RID feed-in tariffs, CER TIP and Cacv
incentives over 20 years, and IVA handling.

The `regime` field selects the incentive stack:

| `regime` | Applies |
|---|---|
| `RID` | feed-in only |
| `CER` | community energy only |
| `RID_CER` | both, combined |

The parameter values behind all of this are in `docs/variables-reference.md`, which is the
reference and is not restated here.

## Persistence is optional

If `DATABASE_URL` is unset the service runs and computes normally; only the storing of
results is lost.
