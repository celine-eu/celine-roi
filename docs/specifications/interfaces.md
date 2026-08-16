# Specifications — the interfaces

What crosses a boundary, in both directions. See [index.md](index.md) for what these
requirements are and are not.

The three boundaries themselves — why they exist and what breaks when one is crossed —
are described in the companion's knowledge. This document states what
is *checked*.

---

## REQ-02xx — the domain/API boundary

Domain objects are frozen dataclasses carrying numpy arrays. They are the computation's
own vocabulary and they are never serialized directly; the `from_domain()` classmethods
on the response schemas are the conversion. Nothing in the type system enforces that.

### REQ-0201 — every domain field is either exposed or declared internal

A field added to a domain dataclass must appear in the matching response schema, or be
listed as deliberately not exposed with a reason. There is no third option in which a
field is added and the response quietly does not carry it.

Currently one field is declared internal: `ProductionData.hourly_production_kwh`, which
would add 8760 floats to every response for a figure the API already reports monthly.

*Verified by* `tests/test_api_boundary.py::TestDomainFieldsReachTheResponse`

### REQ-0202 — no numpy value reaches a client

A serialized scenario response survives `json.dumps` with no custom encoder, and every
numeric value in it is a plain Python `float`. numpy scalars pass Pydantic's float
validation and reach the client looking like numbers a JSON reader then handles
differently — the failure this forbids is silent on both sides.

*Verified by* `tests/test_api_boundary.py::TestNoNumpyCrossesTheBoundary`

### REQ-0203 — the overridable configuration is a closed set

A request may override only a named subset of configuration: WACC, tariffs, the sharing
and virtual-consumption ratios, energy inflation, the load profile and the IRPEF
deduction parameters.

**Tax rates, depreciation schedules and the system's useful life are not overridable.**
They are server policy, not caller input. A caller who could set their own tax rate could
produce any answer it liked and have it come back looking authoritative. An undeclared
key in the request body is ignored rather than merged.

Widening this set is a policy decision, and the test states the set explicitly so that
widening it shows up as a deliberate diff.

*Verified by* `tests/test_api_boundary.py::TestOverridableConfigIsAClosedSet`

### REQ-0204 — overrides never mutate the server's configuration

Applying per-request overrides returns a new dict. The config loaded at startup is shared
by every request, and one request's sensitivity sweep must not become the next request's
defaults.

*Verified by* `tests/test_api_boundary.py::TestOverridesDoNotMutateServerConfig`

### REQ-0205 — domain objects are immutable

Every model in `models.py` is a frozen dataclass; assigning to a field raises. The
pipeline stages hand results to each other and a later stage must not be able to rewrite
an earlier one's output.

*Verified by* `tests/test_models.py::TestSystemInput`,
`tests/test_models.py::TestProductionData`, `tests/test_models.py::TestEnergyResult`,
`tests/test_models.py::TestValidationReport`

---

## REQ-03xx — the external services

`pvgis_client.py` is the only module that reaches the network. Both services it calls are
mocked throughout the suite, so these requirements constrain **this repository's half of
each contract** — what it sends, and how it converts. None of them can detect the
upstream changing.

### REQ-0301 — the Trentino request shape is fixed

A rooftop query posts `{"epsgCode": ..., "wktGeometry": ...}` to the statistics endpoint.
The outbound field names are as much of a contract as the response's, and are the half a
response mock cannot notice going wrong.

*Verified by* `tests/test_external_contracts.py::TestTrentinoRequestContract`

### REQ-0302 — the coordinate system is inferred from the geometry

A WKT polygon with coordinate magnitudes below 1000 is treated as EPSG:4326 (lat/lon);
anything larger is EPSG:25832 (UTM 32N). Magnitude decides, not sign — a western
longitude is still lat/lon. An unparseable geometry defaults to lat/lon.

*Verified by* `tests/test_external_contracts.py::TestDetectEpsg`

### REQ-0303 — the two azimuth conventions are converted, not confused

`SystemInput` uses the PVGIS convention where 0° is south. pvlib uses 0° = north. The
client adds 180° when calling pvlib, so south stays south.

Reversing this is completely silent: the call succeeds and returns the yield of a roof
facing the opposite way, which is a plausible number.

*Verified by* `tests/test_external_contracts.py::TestPvgisAzimuthConvention`

### REQ-0304 — the hourly and monthly series always agree

Both series are derived from the same slice of the PVGIS response. The hourly series is
always 8760 elements — a leap-year TMY returning 8784 rows is truncated before any
aggregation, and a short response is zero-padded — and the monthly series always has 12.
Watts are converted to kWh on the understanding that each row is one hour.

Deriving the two from different slices was a real defect (`a0e7f58`); this is what stops
it recurring.

*Verified by* `tests/test_external_contracts.py::TestPvgisSeriesAreConsistent`

### REQ-0305 — a failing Trentino call degrades visibly

When the Trentino service fails, production falls back to PVGIS and `source` reports
`"pvgis"` rather than `"trentino+pvgis"`. The fallback is otherwise silent — a warning in
the logs and a slightly different number — so `source` is the only thing that lets a
caller tell a working integration from a broken one.

**"Fails" includes returning the wrong shape.** A missing, renamed, null or non-numeric
field is a bad response and is raised as `ValueError` by `trentino_solar.py`, so it takes
the same fallback path as an outage. The exception type is the contract here rather than
an implementation detail: `fetch_production` treats `ValueError` and `ConnectionError` as
"Trentino is no use here". Until 2026-08-15 the client indexed the response dict directly
and leaked `KeyError`, which bypassed the fallback and failed every scenario request for a
Trentino rooftop.

*Verified by* `tests/test_external_contracts.py::TestTrentinoFailureIsVisibleToTheCaller`

### REQ-0306 — the hybrid path scales to the caller's system size

Where a rooftop polygon is supplied for a site in Trentino, the shadow-corrected LIDAR
yield is used even when the caller has also stated a kWp: the roof's production is scaled
from the roof's installable capacity to the caller's, and `effective_kwp` reports the
caller's figure. Where the two agree to within 0.1 kWp, no rescaling is applied.

This widened an earlier rule under which a caller-supplied kWp skipped LIDAR entirely
(`ef42d7d`).

*Verified by* `tests/test_pvgis_client.py::TestFetchProductionHybrid`

### REQ-0307 — production can be supplied instead of fetched

`annual_production_kwh` bypasses both services entirely and distributes the given total
over a synthetic curve. When PVGIS itself is unreachable, the same synthetic path is used
from a specific-yield assumption, and `source` reports `"synthetic"`.

*Verified by* `tests/test_pvgis_client.py::TestFetchProductionSynthetic`,
`tests/test_pvgis_client.py::TestFetchProductionPVGIS`

### REQ-0308 — Trentino coverage is bounded

The LIDAR path is only attempted for coordinates inside Trentino's bounding box, and only
when a rooftop polygon is supplied. An invalid geometry response is raised as an error
carrying the service's own message.

*Verified by* `tests/test_trentino_solar.py::TestIsInTrentino`,
`tests/test_trentino_solar.py::TestFetchTrentinoSolar`

---

## REQ-09xx — scenario comparison

### REQ-0901 — a comparison is a base case plus named variants

`compare` runs the base case and each named scenario, returning every full result
alongside a summary. Each scenario's overrides are separated into those that change the
system and those that change the configuration, and both kinds may appear together.

*Verified by* `tests/test_comparator.py::TestSplitOverrides`,
`tests/test_comparator.py::TestCompareScenarios`

### REQ-0902 — an unusable comparison is rejected, not approximated

An override key belonging to neither the system nor the configuration raises, as does an
empty scenario set. Silently dropping an unrecognised key would produce a comparison in
which two scenarios are quietly identical.

*Verified by* `tests/test_comparator.py::TestCompareScenarios`

### REQ-0903 — the summary names each scenario and shows its delta

The rendered comparison table carries every scenario's name and its difference against
the base case.

*Verified by* `tests/test_comparator.py::TestCompareScenarios`

---

## REQ-10xx — the command line

The CLI runs the same pipeline as the API and is the interface used to sanity-check a
change without starting a server.

### REQ-1001 — the CLI's arguments and defaults are fixed

Required arguments are required, optional ones have the documented defaults, and
`annual_production_kwh` bypasses the production fetch as it does through the API.

*Verified by* `tests/test_cli.py::TestParseArgs`

### REQ-1002 — the exit status reflects validity

A scenario that computes exits 0; one that fails a regulatory check — the SSP regime —
exits 1. The exit status is what makes the CLI usable in a script.

*Verified by* `tests/test_cli.py::TestMain`

### REQ-1003 — the report carries the figures a decision needs

The rendered report contains the header, the NPV, the decision, the year-by-year detail,
the energy summary and the parameters it was run with. A report that omits the parameters
cannot be checked against anything later.

*Verified by* `tests/test_cli.py::TestFormatReport`
