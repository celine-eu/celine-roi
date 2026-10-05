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
widening it shows up as a deliberate diff. A `compare` scenario is held to the same set
(REQ-1308).

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
alongside a summary. Through the API, what a scenario may override is closed (REQ-1308). Each scenario's overrides are separated into those that change the
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

---

## REQ-11xx — ROI feedback

### REQ-1101 — a feedback item belongs to a verified REC membership

The authenticated browser may list only its own Keycloak organizations of type `rec`, and a
submission must name one of them. The backend replaces any community value in diagnostic context
with that verified key before persistence.

*Verified by*
`tests/test_feedback.py::test_participant_lists_own_recs_and_submits_only_to_one_of_them`

### REQ-1102 — feedback retains its diagnostics and optional screenshot

A submission stores its rating, comment, page diagnostics, authenticated subject and optional
screenshot. The screenshot is served separately rather than embedded in list responses.

*Verified by*
`tests/test_feedback.py::test_participant_lists_own_recs_and_submits_only_to_one_of_them`

### REQ-1103 — manager review is authorized for the selected REC

Review requires `community.read` plus `admins` or `managers` in the matching REC organization,
read from that organization's own groups only (`organization.<alias>.groups`). A group held in
another organization counts for nothing here. A platform administrator may review every REC
(REQ-1105). A participant or a manager of another REC is denied before a feedback row or
screenshot is read.

*Rewritten 2026-10-03:* the platform-wide grant was the realm group `admins`; it is now the
realm role `platform-admin` (REQ-1105).

*Verified by*
`tests/test_feedback.py::test_manager_reviews_only_feedback_from_the_authorized_rec`,
`tests/test_feedback.py::TestReviewIsGrantedPerOrganizationOrByThePlatformRole`

### REQ-1105 — only the realm role `platform-admin` reviews every REC

The one grant that reaches every REC's feedback is the Keycloak realm role `platform-admin`, read
from `realm_access.roles`. Nothing else is platform-wide:

- an organization's `admins` group is valid only for that organization's REC;
- a realm group (`/admins`, `admins` in the top-level `groups` claim) grants nothing;
- the retired realm roles `admin`, `manager`, `editor` and `viewer` grant nothing.

`community.read` is still required of a platform administrator.

*Verified by*
`tests/test_feedback.py::TestReviewIsGrantedPerOrganizationOrByThePlatformRole`,
`tests/test_feedback_real_tokens.py::TestRealTokensFromTheLocalRealm`

### REQ-1104 — review state advances monotonically

Manager workflow state is `new` → `seen` → `resolved`; it cannot move backward. List responses
contain per-state counts, and stored subject, IP and user-agent diagnostics are not returned.

*Verified by*
`tests/test_feedback.py::test_manager_reviews_only_feedback_from_the_authorized_rec`

---

## REQ-12xx — deployment posture

### REQ-1201 — outside `CELINE_ENV=dev` the service refuses to start on a development default

`create_app` checks its configuration before the lifespan opens the database pool, through
`celine.sdk.posture`'s `PostureGuard` (`src/celine/roi/posture.py`). It registers:

| Setting | Refused when |
|---|---|
| `DATABASE_URL` | its password is a local-stack password (`securepassword123`, `postgres`) or trivially weak |
| `CELINE_OIDC_BASE_URL`, `CELINE_OIDC_JWKS_URI` | not stated, so the SDK's local Keycloak default is in use |
| `FORWARDED_ALLOW_IPS` | it contains `*` (REQ-1301) |

The signal is `CELINE_ENV`, then `ENVIRONMENT`; the first non-empty one wins. **Only `dev`
relaxes**: unset, empty, `staging`, `prod` or a typo is hardened. Hardened, startup raises
`InsecureConfiguration` naming every violation at once; in dev the same list is logged as
one warning and the service starts. `DATABASE_URL=""` (no persistence, REQ-0401) carries
no password and is accepted everywhere. `task run` exports `CELINE_ENV=dev` unless it is
already set.

This check is about configuration only. Which routes require a token is not changed by it.
On the same signal, `/docs`, `/redoc` and `/openapi.json` are not mounted outside dev (`404`)
unless `CELINE_PUBLIC_DOCS=true`.

*Verified by* `tests/test_posture.py::TestOnlyDevAcceptsDevelopmentDefaults`,
`tests/test_api_docs.py`

---

## REQ-13xx — the public surface

The calculators take no token: the service is a public calculator anyone may use before
joining a community. These requirements bound what one anonymous caller can read, store and
cost. The edge in front of the service carries its own rate limit; these hold without it.

### REQ-1301 — the client address is the connection's peer, never a request header

Every address the service records or limits on is `request.client.host` — the peer as
uvicorn resolved it. `X-Forwarded-For` and `X-Real-IP` are written by whoever sends the
request, so neither is read. Behind an ingress, uvicorn replaces the peer with the forwarded
client only when the connection comes from an address in `FORWARDED_ALLOW_IPS` (default
`127.0.0.1`), so setting it to the ingress's range is a deployment requirement: without it
every caller shares the ingress's address and one rate limit. `FORWARDED_ALLOW_IPS=*`
lets any caller pick its own address and is refused outside `CELINE_ENV=dev` (REQ-1201).

*Verified by* `tests/test_public_limits.py::TestTheClientAddressIsThePeer`,
`tests/test_feedback.py::TestTheStoredAddressIsNotTheCallersChoice`

### REQ-1302 — each client address has a per-minute budget

Every `POST` under `/api/v1/` other than feedback is a calculator and shares one budget
per address (`RATE_LIMIT_CALCULATORS_PER_MINUTE`, default 30); `POST /api/v1/feedback`
has its own (`RATE_LIMIT_FEEDBACK_PER_MINUTE`, default 5). Over budget the answer is
**429** with `Retry-After` in seconds. A request counts whether or not it is valid. Reads
are not limited. The budget lives in the process: one replica is the whole service.

*Verified by* `tests/test_public_limits.py::TestCallsArePerAddressRateLimited`

### REQ-1303 — request bodies are bounded

A calculator body over `MAX_BODY_BYTES_CALCULATORS` (64 KiB) and a feedback body over
`MAX_BODY_BYTES_FEEDBACK` (4 MiB) is refused with **413**, whether the size is declared
or the body is chunked, before the route parses it.

*Verified by* `tests/test_public_limits.py::TestBodiesAreBounded`

### REQ-1304 — stored estimates are readable only by a platform administrator

An estimate holds what an anonymous caller typed — a location, a household's hourly
consumption, a budget. `GET /estimates` and `GET /estimates/{id}` require a token with the
realm role `platform-admin` (as REQ-1105): **401** without a token, **403** without the
role. Nothing else in the platform reads them.

*Verified by* `tests/test_public_inputs.py::TestStoredEstimatesArePlatformAdminOnly`

### REQ-1305 — what one call can store, and compute, is bounded

- An estimate stores the request and the response's **summary** — per scenario for
  `compare` — never the hourly series the caller already received. A full `scenario`
  response is ~650 KiB; what is stored is a few hundred bytes.
- Above `ESTIMATES_MAX_WRITES_PER_MINUTE` (default 60) stored estimates per minute for the
  whole process, the caller still gets its result and nothing is stored; a warning is
  logged.
- `compare` takes 1 to 6 scenarios, with names of at most 100 characters.
- A feedback screenshot is at most 2 MiB decoded; `rooftop_wkt` at most 20 000 characters.

*Verified by* `tests/test_public_inputs.py::TestStorageIsBounded`

### REQ-1306 — the caller's address is stored for reference, and cleared after a retention

`scenario` and `compare` store the caller's address (REQ-1301) with the estimate, as
feedback already did. It is personal data kept for reference only, so it is cleared from
estimates and feedback once older than `CLIENT_IP_RETENTION_DAYS` (default 30), at startup
and hourly after; the row itself stays.

*Verified by* `tests/test_public_inputs.py::TestTheCallerAddressIsStored`,
`tests/test_estimates.py::TestClientAddressRetention`

### REQ-1307 — a load profile is named, never addressed

Every profile a request can name — `config_overrides.load_profile`, and the configured
`load_profile`, `load_profile_by_type` and `heat_pump_profile` — resolves to an existing
entry of `config/load_profiles/` with a plain name (one segment, no leading dot, no `..`,
no link out of the directory). Anything else is **400** with a message that carries the
name at most, never a path. The meter-data folder (`custom_profile_dir`) is not part of the
API: the calculator processes meter exports in the browser and sends hourly values.

*Verified by* `tests/test_public_inputs.py::TestProfilesAreNamedNotAddressed`

### REQ-1308 — a comparison scenario may vary only what a request could set

Each `compare` scenario's overrides are limited to the fields of the system input and of
`config_overrides` (REQ-0203), plus `optimize_profile`, and are validated with the same
bounds as a request of their own. Tax rates, depreciation, the useful life and the profile
maps are not overridable here either, and coordinates stay in Italy.

*Verified by* `tests/test_public_inputs.py::TestComparisonOverridesAreRequestFields`
