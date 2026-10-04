"""What one anonymous caller can cost the public service (REQ-1301 … REQ-1303)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from celine.roi.api.app import create_app
from celine.roi.api.deps import client_ip
from celine.roi.api.limits import FixedWindowLimiter
from celine.roi.posture import posture_guard
from celine.roi.settings import settings

from .test_posture import deployed_settings

CAPEX = "/api/v1/capex-estimate"


def _request(peer: tuple[str, int] | None, headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": peer,
        }
    )


@pytest.fixture()
def app_with(monkeypatch):
    def build(**overrides) -> TestClient:
        monkeypatch.setattr(settings, "database_url", "")
        for name, value in overrides.items():
            monkeypatch.setattr(settings, name, value)
        return TestClient(create_app())

    return build


class TestTheClientAddressIsThePeer:
    """@verifies REQ-1301"""

    def test_a_forwarded_header_is_never_read(self) -> None:
        request = _request(("203.0.113.7", 5000), {"X-Forwarded-For": "198.51.100.1"})
        assert client_ip(request) == "203.0.113.7"

    def test_no_peer_is_none_not_a_header(self) -> None:
        assert client_ip(_request(None, {"X-Forwarded-For": "198.51.100.1"})) is None

    @pytest.mark.parametrize("value", ["*", "10.0.0.1, *"])
    def test_trusting_every_proxy_is_refused_outside_dev(self, value: str) -> None:
        settings_ = deployed_settings(forwarded_allow_ips=value)
        hardened = posture_guard(settings_, env="staging").violations
        assert [v.setting for v in hardened] == ["FORWARDED_ALLOW_IPS"]
        assert posture_guard(settings_, env="dev").violations != []  # warned, not refused

    def test_an_explicit_proxy_list_is_accepted(self) -> None:
        settings_ = deployed_settings(forwarded_allow_ips="10.42.0.0/16")
        assert posture_guard(settings_, env="staging").violations == []


class TestCallsArePerAddressRateLimited:
    """@verifies REQ-1302"""

    def test_the_window_counts_per_key_and_resets(self) -> None:
        now = [0.0]
        limiter = FixedWindowLimiter(2, clock=lambda: now[0])
        assert limiter.hit("a") is None
        assert limiter.hit("a") is None
        assert limiter.hit("a") == 60
        assert limiter.hit("b") is None
        now[0] = 45.2
        assert limiter.hit("a") == 15
        now[0] = 60.0
        assert limiter.hit("a") is None

    def test_over_the_limit_is_429_with_retry_after(self, app_with) -> None:
        with app_with(rate_limit_calculators_per_minute=2) as client:
            codes = [client.post(CAPEX, json={"rooftop_area_m2": 40}).status_code
                     for _ in range(3)]
            last = client.post(CAPEX, json={"rooftop_area_m2": 40})
        assert codes[:2] == [200, 200]
        assert codes[2] == 429
        assert last.status_code == 429
        assert 1 <= int(last.headers["retry-after"]) <= 60

    def test_a_rejected_request_still_counts(self, app_with) -> None:
        with app_with(rate_limit_calculators_per_minute=1) as client:
            assert client.post(CAPEX, json={}).status_code == 400
            assert client.post(CAPEX, json={"rooftop_area_m2": 40}).status_code == 429

    def test_feedback_has_its_own_budget(self, app_with) -> None:
        with app_with(rate_limit_calculators_per_minute=1, rate_limit_feedback_per_minute=1) as c:
            assert c.post(CAPEX, json={"rooftop_area_m2": 40}).status_code == 200
            assert c.post(CAPEX, json={"rooftop_area_m2": 40}).status_code == 429
            # unauthenticated, so 401 — but it was let through, not limited
            assert c.post("/api/v1/feedback", json={}).status_code == 401
            assert c.post("/api/v1/feedback", json={}).status_code == 429

    def test_reads_are_not_limited(self, app_with) -> None:
        with app_with(rate_limit_calculators_per_minute=1) as client:
            assert all(client.get("/openapi.json").status_code == 200 for _ in range(3))


class TestBodiesAreBounded:
    """@verifies REQ-1303"""

    def test_a_declared_oversized_body_is_413(self, app_with) -> None:
        with app_with(max_body_bytes_calculators=1024) as client:
            response = client.post(
                CAPEX, content=b"{" + b" " * 2048 + b"}",
                headers={"content-type": "application/json"},
            )
        assert response.status_code == 413

    def test_a_chunked_oversized_body_is_413(self, app_with) -> None:
        def chunks():
            for _ in range(8):
                yield b" " * 256

        with app_with(max_body_bytes_calculators=1024) as client:
            response = client.post(
                CAPEX, content=chunks(), headers={"content-type": "application/json"}
            )
        assert response.status_code == 413

    def test_a_body_under_the_cap_reaches_the_route(self, app_with) -> None:
        def chunks():
            yield b'{"rooftop_area_m2":'
            yield b" 40}"

        with app_with(max_body_bytes_calculators=1024) as client:
            response = client.post(
                CAPEX, content=chunks(), headers={"content-type": "application/json"}
            )
        assert response.status_code == 200
