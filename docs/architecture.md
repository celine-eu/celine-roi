# Architecture

`celine-roi` is a financial decision engine for Italian photovoltaic installations. Given
system specifications — kWp, location, CAPEX, consumption — it returns 25-year financial
projections under Italian incentive regimes.

Its financial pipeline is a **pure computation service**: it owns no data schema shared with
other components and calls no other CELINE service. Alongside that pipeline, the service owns the
feedback submitted from its browser application, scoped to the caller's Keycloak REC membership.

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
| `api/routes/feedback.py` | authenticated feedback submission and REC-scoped manager review |
| `config/*.yaml` | the parameters, merged flat at startup by `config_loader.py` |

The source tree itself is the reference for what exists; this table is about what each
layer is *for*. What must not cross between them is in the companion's knowledge.

## External calls

`pvgis_client.py` is the **only computation path** that reaches the network: the EU
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

## Persistence and feedback

If `DATABASE_URL` is set to the empty string the service runs and computes normally; only
the storing of results is lost. Unset selects the local development database, which is
accepted only with `CELINE_ENV=dev` (REQ-0404, REQ-1201). Feedback, unlike calculation, inherently requires persistence: its endpoints
return 503 when persistence is explicitly disabled.

A stored estimate keeps the request, the response's summary and the caller's address, which
is cleared after a retention; only the realm role `platform-admin` reads them back
(REQ-1304 … REQ-1306).

The feedback row stores its REC key as a first-class column. The browser may choose only one of the
REC organizations in its verified token. Reading screenshots and advancing an item from `new` to
`seen` to `resolved` additionally requires `community.read` and either a matching REC
`admins`/`managers` group of that same REC organization, or the realm role `platform-admin` (REQ-1105).
A realm group grants nothing. `celine-community` repeats its
own REC authorization before proxying these manager operations; neither service reads the other's
database.
