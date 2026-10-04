"""What an anonymous caller can read, store and name (REQ-1304 … REQ-1308)."""

from __future__ import annotations

import base64
import uuid

import pytest
from celine.sdk.auth import JwtUser
from fastapi.testclient import TestClient

from celine.roi.api.app import create_app
from celine.roi.api.deps import get_user_from_request
from celine.roi.api.routes import _persist
from celine.roi.load_profiles import resolve_profile
from celine.roi.settings import settings

from .conftest import CONFIG_DIR, as_platform_admin

SYSTEM = {
    "kwp": 6.0,
    "latitude": 46.0,
    "longitude": 11.0,
    "capex": 9000.0,
    "annual_consumption_kwh": 3500.0,
    # Supplied so nothing here reaches PVGIS.
    "annual_production_kwh": 7000.0,
}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def saved(monkeypatch) -> list[dict]:
    """Capture what would be written, with a pool that is never touched."""
    rows: list[dict] = []

    async def fake_save(**kwargs):
        rows.append(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(_persist, "get_pool", lambda: object())
    monkeypatch.setattr(_persist, "save_estimate", fake_save)
    monkeypatch.setattr(_persist, "_writes", _persist.FixedWindowLimiter(1000))
    return rows


class TestStoredEstimatesArePlatformAdminOnly:
    """@verifies REQ-1304"""

    PATHS = ["/api/v1/estimates", f"/api/v1/estimates/{uuid.uuid4()}"]

    @pytest.mark.parametrize("path", PATHS)
    def test_anonymous_is_401(self, client, path) -> None:
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("path", PATHS)
    def test_a_user_without_the_role_is_403(self, monkeypatch, path) -> None:
        monkeypatch.setattr(settings, "database_url", "")
        app = create_app()
        claims = {
            "sub": "u",
            "realm_access": {"roles": ["admin", "manager"]},
            "groups": ["/admins"],
        }
        app.dependency_overrides[get_user_from_request] = lambda: JwtUser(
            sub="u", organizations=[], claims=claims
        )
        with TestClient(app) as c:
            assert c.get(path).status_code == 403

    @pytest.mark.parametrize("path", PATHS)
    def test_the_platform_admin_role_gets_through(self, monkeypatch, path) -> None:
        monkeypatch.setattr(settings, "database_url", "")
        with TestClient(as_platform_admin(create_app())) as c:
            assert c.get(path).status_code == 503  # past auth; no store configured


class TestStorageIsBounded:
    """@verifies REQ-1305"""

    def test_a_scenario_stores_its_summary_not_its_series(self, client, saved) -> None:
        response = client.post("/api/v1/scenario", json={"system": SYSTEM})
        assert response.status_code == 200
        [row] = saved
        assert row["response"] == {"summary": response.json()["summary"]}
        assert len(str(row["response"])) < 2_000 < len(response.text)

    def test_a_comparison_stores_each_summary(self, client, saved) -> None:
        response = client.post(
            "/api/v1/compare",
            json={"system": SYSTEM, "scenarios": {"base": {}, "cer": {"regime": "RID_CER"}}},
        )
        assert response.status_code == 200, response.text
        [row] = saved
        assert set(row["response"]["scenarios"]) == {"base", "cer"}
        assert row["response"]["scenarios"]["cer"] == {
            "summary": response.json()["scenarios"]["cer"]["summary"]
        }
        assert row["response"]["summary_table"] == response.json()["summary_table"]

    async def test_above_the_write_ceiling_nothing_is_stored(self, saved, monkeypatch) -> None:
        monkeypatch.setattr(settings, "estimates_max_writes_per_minute", 2)
        for _ in range(4):
            await _persist.persist_estimate(
                endpoint="scenario", status="success", request_body={},
                response_body={"summary": {}}, duration_ms=1, client_ip="203.0.113.7",
            )
        assert len(saved) == 2

    def test_more_than_six_scenarios_is_400(self, client) -> None:
        scenarios = {f"s{i}": {} for i in range(7)}
        response = client.post("/api/v1/compare", json={"system": SYSTEM, "scenarios": scenarios})
        assert response.status_code == 400

    def test_an_oversized_screenshot_is_rejected(self) -> None:
        from celine.roi.api.schemas import SCREENSHOT_MAX_BASE64, FeedbackScreenshotPayload

        at_cap = base64.b64encode(b"x" * (2 * 1024 * 1024)).decode()
        assert len(at_cap) == SCREENSHOT_MAX_BASE64
        FeedbackScreenshotPayload(data_base64=at_cap)
        with pytest.raises(ValueError):
            FeedbackScreenshotPayload(data_base64=at_cap + "AAAA")


class TestTheCallerAddressIsStored:
    """@verifies REQ-1306"""

    def test_scenario_records_the_peer(self, client, saved) -> None:
        client.post(
            "/api/v1/scenario", json={"system": SYSTEM},
            headers={"X-Forwarded-For": "198.51.100.1"},
        )
        assert saved[0]["client_ip"] == "testclient"


class TestProfilesAreNamedNotAddressed:
    """@verifies REQ-1307"""

    PROFILES = CONFIG_DIR / "load_profiles"

    def test_a_shipped_profile_resolves(self) -> None:
        assert resolve_profile(self.PROFILES, "residential_default.json").is_file()

    @pytest.mark.parametrize(
        "name",
        ["../defaults.yaml", "../../etc/hosts", "/etc/hosts", ".hidden", "a/b.json", "", "x" * 101],
    )
    def test_anything_but_a_plain_name_is_refused_without_a_path(self, name) -> None:
        with pytest.raises(ValueError) as exc:
            resolve_profile(self.PROFILES, name)
        assert str(self.PROFILES.resolve()) not in str(exc.value)
        assert "/" not in str(exc.value)

    def test_an_unknown_name_is_refused_without_a_path(self) -> None:
        with pytest.raises(ValueError, match="^Unknown load profile: nope.json$"):
            resolve_profile(self.PROFILES, "nope.json")

    def test_a_link_out_of_the_directory_is_refused(self, tmp_path) -> None:
        profiles = tmp_path / "load_profiles"
        profiles.mkdir()
        (tmp_path / "outside.json").write_text("{}")
        (profiles / "escape.json").symlink_to(tmp_path / "outside.json")
        with pytest.raises(ValueError, match="Unknown load profile"):
            resolve_profile(profiles, "escape.json")

    def test_custom_profile_dir_is_not_part_of_the_api(self, client) -> None:
        from celine.roi.api.schemas import SystemInputRequest

        assert "custom_profile_dir" not in SystemInputRequest.model_fields
        body = {"system": {**SYSTEM, "custom_profile_dir": "anything"}}
        assert client.post("/api/v1/scenario", json=body).status_code == 200

    def test_a_load_profile_override_must_be_a_profile_name(self, client) -> None:
        bad = {"system": SYSTEM, "config_overrides": {"load_profile": "../defaults.yaml"}}
        response = client.post("/api/v1/scenario", json=bad)
        assert response.status_code == 400
        unknown = {"system": SYSTEM, "config_overrides": {"load_profile": "nope.json"}}
        response = client.post("/api/v1/scenario", json=unknown)
        assert response.status_code == 400
        assert response.json()["detail"] == "Unknown load profile: nope.json"


class TestComparisonOverridesAreRequestFields:
    """@verifies REQ-1308"""

    def _compare(self, client, overrides: dict):
        return client.post(
            "/api/v1/compare", json={"system": SYSTEM, "scenarios": {"base": {}, "v": overrides}}
        )

    def test_what_the_calculator_sends_is_accepted(self, client) -> None:
        response = client.post(
            "/api/v1/compare",
            json={
                "system": SYSTEM,
                "scenarios": {
                    "current": {},
                    "cer": {"regime": "RID_CER"},
                    "heat pump": {"optimize_profile": True, "heat_pump_kwh_annual": 3500},
                    "battery": {"forced_tasso_autoconsumo": 0.75},
                },
            },
        )
        assert response.status_code == 200, response.text

    @pytest.mark.parametrize(
        "overrides",
        [
            {"ires": 0.0},  # tax policy (REQ-0203)
            {"irap": 0.0},
            {"useful_life": 400},
            {"heat_pump_profile": "../defaults.yaml"},
            {"load_profile_by_type": {"residential": "../defaults.yaml"}},
            {"custom_profile_dir": "anything"},
        ],
    )
    def test_server_policy_is_not_overridable(self, client, overrides) -> None:
        assert self._compare(client, overrides).status_code == 400

    @pytest.mark.parametrize(
        "overrides",
        [
            {"latitude": 60.0},  # outside the request's bounds, so outside Italy
            {"kwp": 1e9},
            {"wacc": 5.0},
            {"load_profile": "../defaults.yaml"},
            {"optimize_profile": "yes"},
        ],
    )
    def test_values_keep_the_request_bounds(self, client, overrides) -> None:
        assert self._compare(client, overrides).status_code == 400
