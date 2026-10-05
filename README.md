# CELINE ROI Calculator

Financial decision engine for Italian PV systems. Computes ROI projections, energy production estimates, CER incentives, CAPEX estimates, and financial analysis for photovoltaic installations. Persists scenario results for later retrieval.

The UI lives in [celine-frontend](https://github.com/celine-eu/celine-frontend) `apps/roi`.

## Features

- PV energy production estimation via PVGIS and Trentino Solar APIs
- Italian CER (Comunita Energetica Rinnovabile) incentive calculation
- Financial analysis: NPV, IRR, payback period over configurable horizons
- CAPEX estimation with panel specifications and cost curves
- Scenario comparison across multiple configurations
- Estimate persistence (save, list, retrieve)
- Input validation with detailed error reporting
- IRPEF tax deduction modeling
- Battery and heat pump integration support
- Alembic-managed database migrations

## API

All endpoints are under `/api/v1`. Interactive docs at `/docs` (in `CELINE_ENV=dev`, or with `CELINE_PUBLIC_DOCS=true`).

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/production` | POST | Estimate PV energy production |
| `/api/v1/energy` | POST | Compute energy balance with consumption |
| `/api/v1/incentives` | POST | Calculate CER incentives |
| `/api/v1/finance` | POST | Financial analysis (NPV, IRR, payback) |
| `/api/v1/capex-estimate` | POST | Estimate CAPEX from panel specs |
| `/api/v1/validate` | POST | Validate input parameters |
| `/api/v1/scenario` | POST | Run full scenario (production + energy + incentives + finance) |
| `/api/v1/compare` | POST | Compare multiple scenarios side by side |
| `/api/v1/estimates` | GET | List saved estimates (realm role `platform-admin`) |
| `/api/v1/estimates/{id}` | GET | Retrieve a saved estimate (realm role `platform-admin`) |
| `/health` | GET | Health check |

## Quick Start

```bash
uv sync
uv run alembic upgrade head
CELINE_ENV=dev uv run uvicorn celine.roi.api.app:create_app --factory --reload --port 8013
# or: task run   (port 8018, sets CELINE_ENV=dev unless it is already set)
```

## Environment

| Variable | Purpose | Default |
|---|---|---|
| `CELINE_ENV` | Deployment posture; only `dev` accepts the development defaults below (`ENVIRONMENT` is read when it is unset) | unset = **hardened** |
| `DATABASE_URL` | PostgreSQL for estimates and feedback; `""` disables persistence | local stack, dev password (dev only) |
| `CELINE_OIDC_BASE_URL`, `CELINE_OIDC_JWKS_URI` | Issuer and keys tokens are verified against | SDK's local Keycloak (dev only) |
| `CELINE_OIDC_AUDIENCE`, `CELINE_OIDC_CLIENT_ID` | Expected audience | `oauth2_proxy` |
| `FORWARDED_ALLOW_IPS` | Proxies whose `X-Forwarded-For` uvicorn trusts; set it to the ingress's range; `*` is refused outside dev | `127.0.0.1` |
| `RATE_LIMIT_CALCULATORS_PER_MINUTE`, `RATE_LIMIT_FEEDBACK_PER_MINUTE` | Requests per client address per minute | 30, 5 |
| `MAX_BODY_BYTES_CALCULATORS`, `MAX_BODY_BYTES_FEEDBACK` | Largest request body | 64 KiB, 4 MiB |
| `ESTIMATES_MAX_WRITES_PER_MINUTE` | Stored estimates per minute, above which results are served but not stored | 60 |
| `CLIENT_IP_RETENTION_DAYS` | Age after which a stored client address is cleared | 30 |

Outside `CELINE_ENV=dev` — including when it is unset — the service refuses to start while
`DATABASE_URL` carries the local stack's password or the OIDC issuer/JWKS are left at the
SDK's local default, or `FORWARDED_ALLOW_IPS` contains `*`, and lists every such setting
at once (REQ-1201). `CELINE_ENV=staging
task run` is the prod-like mode of the local runner. The check uses `celine.sdk.posture`,
first released in celine-sdk 2.0.0.

### Public by design

The calculators take no token. What an anonymous caller can cost the service is bounded
per client address — rate limits, body sizes, what is stored — and stored estimates are
readable only with the realm role `platform-admin` (REQ-13xx in
`docs/specifications/interfaces.md`). The client address is the one uvicorn resolves, so
behind an ingress **`FORWARDED_ALLOW_IPS` is a deployment requirement**: without it every
visitor shares the ingress's address and one rate limit.

## Configuration

Configuration is loaded from YAML files under the config directory and can be overridden via API request parameters. Key config files:
- `config.yaml` — main configuration (tariffs, rates, horizons)
- `incentives.yaml` — CER incentive rates and IRPEF deduction parameters
- `panel_specs.yaml` — panel specifications and CAPEX cost curves
- `load_profiles/` — hourly load profiles by consumer type

## Documentation

| Document | Description |
|---|---|
| [User Guide](docs/user-guide.md) | How to use the ROI calculator, input parameters, output format |
| [Variables Reference](docs/variables-reference.md) | All configuration variables, overrides, and formulas |

## License

Apache 2.0 — Copyright © 2025 Spindox Labs
