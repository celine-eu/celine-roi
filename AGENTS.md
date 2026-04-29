# celine-roi

Financial decision engine for Italian PV (photovoltaic) installations. Given system specs (kWp, location, CAPEX, consumption) it runs a multi-phase pipeline and returns 25-year financial projections under Italian incentive regimes (RID, CER, combined).

## Pipeline

The pipeline is a strict chain executed in `main.py:run_scenario`:

```
SystemInput → fetch_production (PVGIS / Trentino Solar) → compute_energy → compute_incentives → compute_finance → validate_model → ScenarioResult
```

Each phase is both a standalone API endpoint (`/api/v1/{phase}`) and a step in the full `/api/v1/scenario` endpoint. The `/api/v1/compare` endpoint runs multiple scenarios side-by-side.

## Source layout

```
src/celine/roi/
├── settings.py          # Pydantic BaseSettings (DATABASE_URL, pool sizes)
├── db.py                # SQLAlchemy DeclarativeBase + Estimate model
├── models.py            # Frozen dataclasses: SystemInput → … → FinanceResult (domain layer, no DB)
├── main.py              # Pipeline orchestrator (run_scenario)
├── config_loader.py     # Merges config/*.yaml into a flat dict
├── pvgis_client.py      # Async HTTP client for PVGIS and Trentino Solar LIDAR
├── trentino_solar.py    # Trentino-specific rooftop polygon → kWp estimation
├── load_profiles.py     # Hourly consumption profile loading (JSON/CSV/meter data)
├── capex_estimator.py   # CAPEX estimation from panel specs
├── engines/
│   ├── energy.py        # Hourly/monthly production-vs-consumption matching
│   ├── incentives.py    # 25-year RID, CER TIP/Cacv, IRPEF deduction, depreciation
│   └── finance.py       # NPV, IRR, payback, DSCR, cumulative cashflows
├── validation/
│   └── warnings.py      # Regulatory and parameter sanity checks
├── scenarios/
│   └── comparator.py    # Multi-scenario side-by-side comparison
├── api/
│   ├── app.py           # FastAPI factory with lifespan (config + DB pool init)
│   ├── entrypoint.py    # uvicorn entry: main() → create_app()
│   ├── database.py      # asyncpg pool + raw SQL queries for estimate persistence
│   ├── deps.py          # FastAPI dependencies (config injection, per-request overrides)
│   ├── schemas.py       # Pydantic v2 request/response models (API boundary)
│   └── routes/          # One file per endpoint: scenario, compare, estimates, production, energy, incentives, finance, capex, validate
```

## Key patterns

### Domain vs API boundary
Domain objects are frozen dataclasses in `models.py` with numpy arrays. They are never serialized directly. Response schemas in `schemas.py` convert via `from_domain()` classmethods, turning numpy arrays into plain lists at the boundary.

### Config system
YAML files in `config/` (`defaults.yaml`, `incentives.yaml`, `tax_rates.yaml`, `panel_specs.yaml`) are merged into a flat dict at startup by `config_loader.py`. Routes receive config via the `ConfigDep` dependency. Per-request overrides are applied through `ConfigOverrides` in the request body — only a subset of parameters is overridable (WACC, tariffs, deduction rates). Tax rates and depreciation schedules are server policy.

### Database (estimates persistence)
- **Optional**: if `DATABASE_URL` is empty/unset the app still works without persistence.
- Uses **asyncpg** directly (no ORM for queries) — parameterized SQL in `database.py`.
- Schema managed by **Alembic** with a SQLAlchemy model in `db.py` as the source of truth.
- The `scenario` and `compare` routes persist results as background tasks via `save_estimate`.
- The `estimates` routes provide read-only access to persisted results.

### Alembic
- `alembic.ini` at repo root, migrations in `alembic/versions/`.
- `alembic/env.py` reads `settings.database_url` from `celine.roi.settings`.
- Tasks: `task alembic:migrate`, `task alembic:sync-model`, `task alembic:reset`.
- When adding/changing DB models in `db.py`, run `task alembic:sync-model` to autogenerate a migration, then review and edit it.

### External API calls
`pvgis_client.py` makes async HTTP calls to the EU PVGIS API and optionally the Trentino Solar LIDAR API. These are the only external network calls the engine makes. Production data can be bypassed by setting `annual_production_kwh` (synthetic distribution) or providing `rooftop_wkt` (Trentino).

### Italian regulatory domain
All financial calculations use Italian-specific parameters: IRPEF deduction (50%/36% depending on primary residence), IRES/IRAP taxation, RID feed-in tariffs, CER TIP/Cacv incentives with 20-year duration, IVA handling. The `regime` field controls which incentive stack applies: `RID` (feed-in only), `CER` (community energy only), or `RID_CER` (combined).

## Running

```bash
task setup              # uv sync
task run                # uvicorn on :8018 with --reload
task debug              # same with debugpy attach
docker compose up       # postgres + alembic migration + app
```

Port mapping: local dev uses `8018`, Docker maps `8018→8000`.

## Testing

```bash
uv run pytest           # all tests
uv run pytest tests/test_scenario.py -k "test_name"
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. Most engine tests are pure (no DB, no network). API integration tests in `test_main.py` use FastAPI's `TestClient`.
