"""The probe target (REQ-1202).

The Kubernetes liveness and readiness probes call `GET /health`. It must answer under
the hardened posture, where the docs are not mounted, with no token, without the
lifespan having opened anything, and however often it is called.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from celine.roi.api.app import create_app
from celine.roi.settings import settings

from .test_posture import explicit_oidc


@pytest.fixture()
def staging(monkeypatch) -> TestClient:
    """The app as staging builds it: real posture check, nothing left at a dev default."""
    monkeypatch.setenv("CELINE_ENV", "staging")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("CELINE_PUBLIC_DOCS", raising=False)
    for name in ("BASE_URL", "JWKS_URI"):
        monkeypatch.delenv(f"CELINE_OIDC_{name}", raising=False)
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "oidc", explicit_oidc())
    monkeypatch.setattr(settings, "rate_limit_calculators_per_minute", 1)
    # No `with`: the lifespan never runs, so no configuration and no pool exist.
    # /health answering here is what shows it depends on neither.
    return TestClient(create_app())


class TestHealthAnswersTheProbe:
    """@verifies REQ-1202"""

    def test_health_answers_without_a_token(self, staging) -> None:
        resp = staging.get("/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_the_docs_stay_unmounted(self, staging) -> None:
        assert [staging.get(p).status_code for p in ("/docs", "/openapi.json")] == [404, 404]

    def test_health_is_not_rate_limited(self, staging) -> None:
        # The calculators' budget is 1 per minute here; a probe calls every few seconds.
        assert [staging.get("/health").status_code for _ in range(5)] == [200] * 5

    def test_health_is_outside_the_api(self, staging) -> None:
        assert staging.get("/api/v1/health").status_code == 404
