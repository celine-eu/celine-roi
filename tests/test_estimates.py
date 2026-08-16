"""Tests for the estimates persistence layer."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://celine:celine@localhost:25432/celine",
)

REPO_ROOT = Path(__file__).parent.parent

try:
    import asyncpg  # noqa: F401
except ImportError:
    pytest.skip("asyncpg not installed", allow_module_level=True)


def _database_is_reachable(url: str) -> bool:
    """TCP-probe the database host named in `url`.

    Done as a socket check rather than by interpreting an Alembic failure, so that a
    genuinely broken migration fails loudly instead of being mistaken for an absent
    database and skipped.
    """
    parsed = urlsplit(url)
    if not parsed.hostname:
        return False
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 5432), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def migrated_schema() -> None:
    """Bring the test database up to head, or skip the whole layer.

    The schema is created by running the Alembic migrations — the same thing
    production runs — rather than by re-declaring the DDL here or building it from
    `db.py`. A fixture that built the schema from the model would pass while a broken
    migration shipped, which is the failure worth catching.

    Alembic reads `settings.database_url`, and `settings` is instantiated at import,
    so the migration runs in a subprocess with DATABASE_URL in its environment rather
    than by mutating this process's already-imported settings.
    """
    if not _database_is_reachable(DATABASE_URL):
        pytest.skip(f"Postgres not reachable at {DATABASE_URL}")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": DATABASE_URL},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")


@pytest.fixture()
async def pool(migrated_schema):
    """Create a temporary asyncpg pool against the migrated test database."""
    try:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    except (OSError, asyncpg.PostgresError):
        pytest.skip("Postgres not reachable")
    yield _pool
    await _pool.close()


@pytest.fixture()
def app_database_url(migrated_schema, monkeypatch) -> str:
    """Point the *application's* pool at the test database.

    Two traps here, both of which this repository's tests fell into before.

    `settings` is a module-level singleton instantiated at import, so
    `monkeypatch.setenv("DATABASE_URL", ...)` is a no-op by the time a test runs — the
    app would quietly query whatever the built-in default names. The attribute has to
    be set on the instance.

    And the app's pool cannot simply be the `pool` fixture: `TestClient` drives the
    application on its own event loop, and an asyncpg pool belongs to the loop that
    created it. The app must build its own pool, through the lifespan, against the
    same database.
    """
    from celine.roi.settings import settings

    monkeypatch.setattr(settings, "database_url", DATABASE_URL)
    return DATABASE_URL


@pytest.fixture()
def api_client(app_database_url):
    """A TestClient, lifespan entered, whose pool is against the test database."""
    from celine.roi.api.app import create_app

    with TestClient(create_app()) as client:
        yield client


# @verifies REQ-0408
class TestMigrationsMatchTheModel:

    async def test_migrated_table_has_the_model_columns(self, pool) -> None:
        """The schema Alembic produces must be the schema `db.py` declares.

        Nothing else keeps these two in step. The SQLAlchemy model is what Alembic
        autogenerates *from*, but the migration is a hand-editable draft afterwards, and
        run-time queries go through asyncpg against whatever actually shipped. A column
        added to the model and forgotten in the migration is invisible until a query
        against it fails in production.
        """
        from celine.roi.db import Estimate

        rows = await pool.fetch(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = $1",
            Estimate.__tablename__,
        )
        assert rows, f"table {Estimate.__tablename__} does not exist after migrating"

        migrated = {r["column_name"] for r in rows}
        declared = {c.name for c in Estimate.__table__.columns}

        assert declared == migrated, (
            "the model and the migrated schema disagree.\n"
            f"  in the model, not in the database: {sorted(declared - migrated)}\n"
            f"  in the database, not in the model: {sorted(migrated - declared)}\n"
            "Autogenerate a migration (`task alembic:sync-model`) and read it before "
            "applying — see .agents/playbooks/changing-the-database-model.md."
        )

    async def test_nullability_matches_the_model(self, pool) -> None:
        from celine.roi.db import Estimate

        rows = await pool.fetch(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = $1",
            Estimate.__tablename__,
        )
        migrated = {r["column_name"]: r["is_nullable"] == "YES" for r in rows}
        declared = {c.name: c.nullable for c in Estimate.__table__.columns}

        mismatched = {
            name: (declared[name], migrated[name])
            for name in declared
            if name in migrated and declared[name] != migrated[name]
        }
        assert not mismatched, (
            f"nullability differs between model and database (declared, migrated): "
            f"{mismatched}"
        )


# @verifies REQ-0406
class TestSaveEstimate:

    async def test_save_and_retrieve_scenario(self, pool) -> None:
        from celine.roi.api.database import get_estimate, save_estimate

        request_data = {"system": {"kwp": 10, "latitude": 46.0}}
        response_data = {"summary": {"npv_eur": 5000}}

        estimate_id = await save_estimate(
            pool=pool,
            endpoint="scenario",
            status="success",
            request=request_data,
            response=response_data,
            duration_ms=1234,
        )

        assert isinstance(estimate_id, uuid.UUID)

        record = await get_estimate(pool, estimate_id)
        assert record is not None
        assert record["endpoint"] == "scenario"
        assert record["status"] == "success"
        assert record["request"] == request_data
        assert record["response"] == response_data
        assert record["duration_ms"] == 1234
        assert record["created_at"] is not None

    async def test_save_error_estimate(self, pool) -> None:
        from celine.roi.api.database import get_estimate, save_estimate

        estimate_id = await save_estimate(
            pool=pool,
            endpoint="scenario",
            status="error",
            request={"system": {"kwp": 10}},
            response=None,
            duration_ms=50,
            error_message="PVGIS unreachable",
        )

        record = await get_estimate(pool, estimate_id)
        assert record["status"] == "error"
        assert record["response"] is None
        assert record["error_message"] == "PVGIS unreachable"

    async def test_get_nonexistent_returns_none(self, pool) -> None:
        from celine.roi.api.database import get_estimate

        record = await get_estimate(pool, uuid.uuid4())
        assert record is None


# @verifies REQ-0407
class TestListEstimates:

    async def test_list_returns_recent_first(self, pool) -> None:
        from celine.roi.api.database import list_estimates, save_estimate

        ids = []
        for idx in range(3):
            eid = await save_estimate(
                pool=pool,
                endpoint="scenario",
                status="success",
                request={"idx": idx},
                response={"summary": {"npv_eur": idx * 1000}},
                duration_ms=100,
            )
            ids.append(eid)

        result = await list_estimates(pool, limit=3, offset=0)
        assert result["total"] >= 3
        assert len(result["items"]) >= 3
        returned_ids = [item["id"] for item in result["items"]]
        assert returned_ids.index(ids[2]) < returned_ids.index(ids[0])

    async def test_list_filter_by_endpoint(self, pool) -> None:
        from celine.roi.api.database import list_estimates, save_estimate

        await save_estimate(
            pool=pool,
            endpoint="compare",
            status="success",
            request={"test": "filter"},
            response={"summary_table": "..."},
            duration_ms=200,
        )

        result = await list_estimates(pool, limit=100, offset=0, endpoint="compare")
        assert result["total"] >= 1
        assert all(item["endpoint"] == "compare" for item in result["items"])

    async def test_list_pagination(self, pool) -> None:
        from celine.roi.api.database import list_estimates

        page1 = await list_estimates(pool, limit=2, offset=0)
        page2 = await list_estimates(pool, limit=2, offset=2)
        if page1["total"] >= 4:
            ids1 = {item["id"] for item in page1["items"]}
            ids2 = {item["id"] for item in page2["items"]}
            assert ids1.isdisjoint(ids2)


# @verifies REQ-0406
class TestEstimatesAPI:

    async def test_get_estimate_by_id(self, pool, api_client) -> None:
        from celine.roi.api.database import save_estimate

        estimate_id = await save_estimate(
            pool=pool,
            endpoint="scenario",
            status="success",
            request={"system": {"kwp": 6}},
            response={"summary": {"npv_eur": 3000, "irr_pct": 9.1}},
            duration_ms=800,
        )

        resp = api_client.get(f"/api/v1/estimates/{estimate_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(estimate_id)
        assert data["endpoint"] == "scenario"
        assert data["request"]["system"]["kwp"] == 6

    async def test_get_estimate_not_found(self, api_client) -> None:
        resp = api_client.get(f"/api/v1/estimates/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_list_estimates(self, pool, api_client) -> None:
        from celine.roi.api.database import save_estimate

        await save_estimate(
            pool=pool,
            endpoint="scenario",
            status="success",
            request={"system": {"kwp": 3}},
            response={"summary": {"npv_eur": 1500}},
            duration_ms=500,
        )

        resp = api_client.get("/api/v1/estimates?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["limit"] == 5

    async def test_list_estimates_db_unavailable(self, monkeypatch) -> None:
        """When pool is None (no DATABASE_URL), GET returns 503."""
        import celine.roi.api.database as db_mod

        monkeypatch.setattr(db_mod, "_pool", None)

        from celine.roi.api.app import create_app

        app = create_app()
        client = TestClient(app)

        resp = client.get("/api/v1/estimates")
        assert resp.status_code == 503


# @verifies REQ-0403
class TestScenarioPersistence:

    async def test_scenario_saves_estimate(self, app_database_url, monkeypatch) -> None:
        """POST /scenario should fire a background task that saves the estimate."""
        import celine.roi.api.database as db_mod
        import celine.roi.api.routes.scenario as scenario_mod

        saved: list[dict] = []
        original_save = db_mod.save_estimate

        async def capture_save(**kwargs):
            result = await original_save(**kwargs)
            saved.append(kwargs)
            return result

        # Patch on the scenario module — the direct import binds there, not on database
        monkeypatch.setattr(scenario_mod, "save_estimate", capture_save)

        from celine.roi.api.app import create_app

        app = create_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/scenario",
                json={
                    "system": {
                        "kwp": 10.0,
                        "latitude": 46.0,
                        "longitude": 11.0,
                        "capex": 12000.0,
                        "annual_consumption_kwh": 5000.0,
                        "annual_production_kwh": 12000.0,
                    }
                },
            )
            assert resp.status_code == 200, resp.text
            assert len(saved) == 1
            assert saved[0]["endpoint"] == "scenario"
            assert saved[0]["status"] == "success"
            assert saved[0]["duration_ms"] >= 0


# @verifies REQ-0403
class TestComparePersistence:

    async def test_compare_saves_estimate(self, app_database_url, monkeypatch) -> None:
        """POST /compare should fire a background task that saves the estimate."""
        import celine.roi.api.database as db_mod
        import celine.roi.api.routes.compare as compare_mod

        saved: list[dict] = []
        original_save = db_mod.save_estimate

        async def capture_save(**kwargs):
            result = await original_save(**kwargs)
            saved.append(kwargs)
            return result

        # Patch on the compare module — the direct import binds there, not on database
        monkeypatch.setattr(compare_mod, "save_estimate", capture_save)

        from celine.roi.api.app import create_app

        app = create_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/compare",
                json={
                    "system": {
                        "kwp": 10.0,
                        "latitude": 46.0,
                        "longitude": 11.0,
                        "capex": 12000.0,
                        "annual_consumption_kwh": 5000.0,
                        "annual_production_kwh": 12000.0,
                    },
                    "scenarios": {
                        "base": {},
                        "optimistic": {"forced_tasso_autoconsumo": 0.7},
                    },
                },
            )

            assert resp.status_code == 200, resp.text
            assert len(saved) == 1
            assert saved[0]["endpoint"] == "compare"
            assert saved[0]["status"] == "success"
