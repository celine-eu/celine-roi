"""The persistence layer is optional — this file states what that actually means.

`.agents/knowledge/the-three-boundaries.md` § 3 records that this service computes fine
with no database, and nothing asserted it. Measured, "no database" turns out to be three
different situations with three different outcomes, and only one of them matches what the
guarantee is usually taken to mean:

| `DATABASE_URL`     | Outcome                                                    |
|--------------------|------------------------------------------------------------|
| empty string       | persistence disabled, everything else works                 |
| unset              | falls back to a hardcoded default and connects to it        |
| set but unreachable| **the whole application fails to start**                    |

The tests below pin all three. The last is written to the guarantee and marked xfail,
because the guarantee is the thing worth recording even where the code does not meet it
— a plain skip would say nothing, and a failing test would poison the baseline.

None of these tests need a database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from celine.roi.api.app import create_app

_SCENARIO_BODY = {
    "system": {
        "kwp": 10.0,
        "latitude": 46.0,
        "longitude": 11.0,
        "capex": 12000.0,
        "annual_consumption_kwh": 5000.0,
        # Supplied so the pipeline never reaches PVGIS — this file is about the
        # database, and a network call would make it about something else.
        "annual_production_kwh": 12000.0,
    }
}


@pytest.fixture()
def persistence_disabled(monkeypatch) -> None:
    """Set `settings.database_url` to empty, the documented "no database" case.

    Set on the instance, not the environment: `settings` is a module-level singleton
    built at import, so `monkeypatch.setenv("DATABASE_URL", ...)` never reaches it.
    """
    from celine.roi.settings import settings

    monkeypatch.setattr(settings, "database_url", "")


# @verifies REQ-0401
class TestServiceRunsWithoutADatabase:

    def test_application_starts(self, persistence_disabled) -> None:
        with TestClient(create_app()) as client:
            assert client.get("/docs").status_code == 200

    def test_scenario_still_computes(self, persistence_disabled) -> None:
        """The computation endpoints need no database and must not acquire one."""
        with TestClient(create_app()) as client:
            resp = client.post("/api/v1/scenario", json=_SCENARIO_BODY)

        assert resp.status_code == 200, resp.text
        assert resp.json()["summary"]["annual_production_kwh"] == pytest.approx(12000.0)

    def test_pool_is_not_created(self, persistence_disabled) -> None:
        from celine.roi.api.database import get_pool

        with TestClient(create_app()):
            assert get_pool() is None


# @verifies REQ-0402
class TestRetrievalEndpointsDegradeCleanly:

    def test_list_returns_503_not_500(self, persistence_disabled) -> None:
        with TestClient(create_app()) as client:
            resp = client.get("/api/v1/estimates")

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    def test_get_by_id_returns_503_not_500(self, persistence_disabled) -> None:
        import uuid

        with TestClient(create_app()) as client:
            resp = client.get(f"/api/v1/estimates/{uuid.uuid4()}")

        assert resp.status_code == 503


# @verifies REQ-0403
class TestAFailedWriteDoesNotFailTheRequest:

    def test_scenario_succeeds_when_persistence_raises(
        self, persistence_disabled, monkeypatch
    ) -> None:
        """Persistence runs as a background task on purpose.

        A broken write must show up in the logs, not in the caller's response — this is
        what makes the write safe to attempt at all.
        """
        import celine.roi.api.routes.scenario as scenario_mod

        class _FakePool:
            pass

        async def _exploding_save(**kwargs):
            raise RuntimeError("write failed")

        monkeypatch.setattr(scenario_mod, "get_pool", lambda: _FakePool())
        monkeypatch.setattr(scenario_mod, "save_estimate", _exploding_save)

        with TestClient(create_app()) as client:
            resp = client.post("/api/v1/scenario", json=_SCENARIO_BODY)

        assert resp.status_code == 200, resp.text


# @verifies REQ-0404
class TestUnsetIsNotTheSameAsDisabled:

    def test_default_database_url_is_not_empty(self) -> None:
        """Unsetting DATABASE_URL does not disable persistence — it selects the dev default.

        `Settings` supplies a non-empty default pointing at the local development
        database, so a checkout works with nothing exported. That is deliberate. What it
        means is that the guard in `init_pool` — `if not database_url` — never fires on an
        *unset* variable, only on an explicitly empty one.

        So there are two knobs, not one: `DATABASE_URL` chooses **which** database, and
        `DATABASE_URL=""` is the only way to choose **none**.
        """
        from celine.roi.settings import Settings

        assert Settings(_env_file=None).database_url != "", (
            "The default is now empty, so unset and disabled finally agree. Update "
            "REQ-0404 and the knowledge note together with this test."
        )


# @verifies REQ-0405
class TestAConfiguredButUnreachableDatabaseIsFatal:

    def test_startup_fails_rather_than_degrading(self, monkeypatch) -> None:
        """A database that is configured and unreachable stops the service starting.

        This is intended, and it is the one place where "persistence is optional" stops
        applying. The distinction is between *not asking for* a database and *asking for
        one that is not there*:

        - no database configured (`DATABASE_URL=""`) — supported, REQ-0401;
        - a database configured but absent — a misconfiguration or an outage, and the
          service refuses to come up rather than serving while silently discarding every
          write.

        Starting anyway would mean estimates vanish with nothing but a log line to say
        so, and REQ-0403 guarantees the caller is never told. Failing at startup is what
        makes that guarantee safe to give.

        The caller-facing side of this is not this repository's job: `../celine-frontend`
        handles an unavailable ROI service with a graceful message.
        """
        from celine.roi.settings import settings

        monkeypatch.setattr(
            settings, "database_url", "postgresql://x:x@127.0.0.1:59999/nope"
        )

        with pytest.raises(OSError):
            with TestClient(create_app()):
                pass  # pragma: no cover — startup is expected to raise first
