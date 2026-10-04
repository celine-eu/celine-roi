"""REC ownership and authorization for ROI feedback."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

import pytest
from celine.sdk.auth import JwtUser
from celine.sdk.auth.jwt import Organization
from fastapi.testclient import TestClient

from celine.roi.api.app import create_app
from celine.roi.api.deps import get_user_from_request

COMMUNITY_KEY = "example_rec"
FEEDBACK_ID = uuid.UUID("7d92f843-68f8-44b4-ac90-7742a6c228e9")


def _user(*, manager: bool = False, community_key: str = COMMUNITY_KEY) -> JwtUser:
    groups = ["/managers"] if manager else ["/participants"]
    org_claim = {community_key: {"type": ["rec"], "groups": groups}}
    claims = {
        "sub": "roi-feedback-user",
        "scope": "community.read",
        "organization": org_claim,
    }
    return JwtUser(
        sub="roi-feedback-user",
        organizations=[Organization._from_claim(community_key, org_claim[community_key])],
        claims=claims,
    )


@pytest.fixture()
def client(monkeypatch):
    from celine.roi.settings import settings

    monkeypatch.setattr(settings, "database_url", "")
    app = create_app()
    app.dependency_overrides[get_user_from_request] = _user
    with TestClient(app) as test_client:
        yield test_client, app


def _payload(community_key: str = COMMUNITY_KEY) -> dict:
    return {
        "community_key": community_key,
        "rating": 4,
        "comment": "Il confronto economico è chiaro",
        "context": {
            "page_url": "http://roi.celine.localhost/",
            "page_title": "Calcolatore ROI",
            "page_path": "/",
            "locale": "it",
            "extra": {"community_key": "untrusted"},
        },
        "screenshot": {
            "mime_type": "image/webp",
            "data_base64": base64.b64encode(b"roi-screen").decode(),
        },
    }


def _item(status: str = "new") -> dict:
    return {
        "id": FEEDBACK_ID,
        "rating": 4,
        "comment": "Il confronto economico è chiaro",
        "page_url": "http://roi.celine.localhost/",
        "page_title": "Calcolatore ROI",
        "page_path": "/",
        "extra": {},
        "has_screenshot": True,
        "status": status,
        "seen_at": datetime.now(UTC) if status != "new" else None,
        "resolved_at": datetime.now(UTC) if status == "resolved" else None,
        "created_at": datetime.now(UTC),
    }


def test_participant_lists_own_recs_and_submits_only_to_one_of_them(
    client, monkeypatch
) -> None:
    """@verifies REQ-1101 REQ-1102"""
    test_client, _ = client
    stored: dict = {}

    async def fake_save(pool, **kwargs):
        stored.update(kwargs)
        return {"id": FEEDBACK_ID, "created_at": datetime.now(UTC)}

    import celine.roi.api.routes.feedback as feedback_routes

    monkeypatch.setattr(feedback_routes, "get_pool", lambda: object())
    monkeypatch.setattr(feedback_routes, "save_feedback", fake_save)

    communities = test_client.get("/api/v1/feedback/communities")
    created = test_client.post("/api/v1/feedback", json=_payload())
    denied = test_client.post("/api/v1/feedback", json=_payload("another-rec"))
    manager_inbox_denied = test_client.get(f"/api/v1/feedback/manager/{COMMUNITY_KEY}")

    assert communities.status_code == 200
    assert communities.json() == {"communities": [COMMUNITY_KEY]}
    assert created.status_code == 201
    assert stored["community_key"] == COMMUNITY_KEY
    assert stored["context"]["extra"]["community_key"] == COMMUNITY_KEY
    assert stored["screenshot_bytes"] == b"roi-screen"
    assert denied.status_code == 403
    assert manager_inbox_denied.status_code == 403


def test_manager_reviews_only_feedback_from_the_authorized_rec(client, monkeypatch) -> None:
    """@verifies REQ-1103 REQ-1104"""
    test_client, app = client
    app.dependency_overrides[get_user_from_request] = lambda: _user(manager=True)
    current_status = {"value": "new"}

    async def fake_list(pool, community_key, **kwargs):
        return {
            "community_key": community_key,
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
            "total": 1,
            "counts": {"new": 1, "seen": 0, "resolved": 0},
            "items": [_item()],
        }

    async def fake_screenshot(pool, community_key, feedback_id):
        return {"screenshot_bytes": b"roi-screen", "screenshot_mime_type": "image/webp"}

    async def fake_status(pool, community_key, feedback_id):
        return current_status["value"]

    async def fake_update(pool, community_key, feedback_id, **kwargs):
        current_status["value"] = kwargs["status"]
        return _item(kwargs["status"])

    import celine.roi.api.routes.feedback as feedback_routes

    monkeypatch.setattr(feedback_routes, "get_pool", lambda: object())
    monkeypatch.setattr(feedback_routes, "list_feedback", fake_list)
    monkeypatch.setattr(feedback_routes, "get_feedback_screenshot", fake_screenshot)
    monkeypatch.setattr(feedback_routes, "get_feedback_status", fake_status)
    monkeypatch.setattr(feedback_routes, "update_feedback_status", fake_update)

    listed = test_client.get(f"/api/v1/feedback/manager/{COMMUNITY_KEY}")
    screenshot = test_client.get(
        f"/api/v1/feedback/manager/{COMMUNITY_KEY}/{FEEDBACK_ID}/screenshot"
    )
    resolved = test_client.patch(
        f"/api/v1/feedback/manager/{COMMUNITY_KEY}/{FEEDBACK_ID}",
        json={"status": "resolved"},
    )
    backward = test_client.patch(
        f"/api/v1/feedback/manager/{COMMUNITY_KEY}/{FEEDBACK_ID}",
        json={"status": "seen"},
    )
    denied = test_client.get("/api/v1/feedback/manager/another-rec")

    assert listed.status_code == 200
    assert listed.json()["items"][0]["has_screenshot"] is True
    assert screenshot.status_code == 200
    assert screenshot.headers["content-type"] == "image/webp"
    assert screenshot.content == b"roi-screen"
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert backward.status_code == 409
    assert denied.status_code == 403


def _user_from_claims(claims: dict) -> JwtUser:
    """A JwtUser built the way `JwtUser.from_token` builds one, without a signature."""
    orgs = claims.get("organization") or {}
    return JwtUser(
        sub=claims.get("sub", "roi-review-user"),
        organizations=[Organization._from_claim(alias, value) for alias, value in orgs.items()],
        claims=claims,
    )


def _claims(
    *,
    roles: list[str] | None = None,
    groups: list[str] | None = None,
    organization: dict | None = None,
    scope: str = "community.read",
    **extra,
) -> dict:
    claims: dict = {"sub": "roi-review-user", "azp": "oauth2_proxy", "scope": scope, **extra}
    if roles is not None:
        claims["realm_access"] = {"roles": roles}
    if groups is not None:
        claims["groups"] = groups
    if organization is not None:
        claims["organization"] = organization
    return claims


OTHER_REC = "another-rec"
DEFAULT_ROLES = ["default-roles-celine", "offline_access", "uma_authorization"]
# The access-token shapes measured on the local realm (celine-dev token kit).
PLATFORM_ADMIN = _claims(roles=["platform-admin"])
ORG_ADMIN = _claims(
    roles=DEFAULT_ROLES,
    organization={COMMUNITY_KEY: {"type": ["rec"], "groups": ["/admins"]}},
)
# The retired shape: realm group /admins in both forms, realm role `admin`, and an
# organisation admins membership in a different organisation.
LEGACY_REALM_ADMIN = _claims(
    roles=["admin"],
    groups=["/admins", "admins"],
    organization={"example-dso": {"type": ["dso"], "groups": ["/admins"]}},
)


class TestReviewIsGrantedPerOrganizationOrByThePlatformRole:
    """Only the realm role `platform-admin` is platform-wide; organisation groups count
    only for their own REC; a realm group or a retired realm role grants nothing.

    @verifies REQ-1103 REQ-1105
    """

    @staticmethod
    def _allowed(claims: dict, community_key: str) -> bool:
        from fastapi import HTTPException

        from celine.roi.api.deps import require_rec_manager

        try:
            require_rec_manager(_user_from_claims(claims), community_key)
        except HTTPException as exc:
            assert exc.status_code == 403
            return False
        return True

    def test_the_platform_admin_role_reviews_every_rec(self) -> None:
        assert self._allowed(PLATFORM_ADMIN, COMMUNITY_KEY)
        assert self._allowed(PLATFORM_ADMIN, OTHER_REC)

    def test_the_platform_admin_role_still_needs_community_read(self) -> None:
        assert not self._allowed(_claims(roles=["platform-admin"], scope="openid"), OTHER_REC)

    def test_an_organisation_admin_reviews_only_its_own_rec(self) -> None:
        assert self._allowed(ORG_ADMIN, COMMUNITY_KEY)
        assert not self._allowed(ORG_ADMIN, OTHER_REC)

    def test_an_organisation_admin_is_not_a_platform_admin(self) -> None:
        many = _claims(
            roles=DEFAULT_ROLES,
            organization={
                COMMUNITY_KEY: {"type": ["rec"], "groups": ["/admins"]},
                "example_dso": {"type": ["dso"], "groups": ["/admins"]},
            },
        )
        assert not self._allowed(many, OTHER_REC)
        # admins of a DSO organisation do not make its alias a reviewable REC either
        assert not self._allowed(many, "example_dso")

    def test_a_legacy_realm_group_grants_nothing(self) -> None:
        assert not self._allowed(LEGACY_REALM_ADMIN, COMMUNITY_KEY)
        assert not self._allowed(LEGACY_REALM_ADMIN, OTHER_REC)
        assert not self._allowed(_claims(groups=["/admins", "admins"]), COMMUNITY_KEY)

    @pytest.mark.parametrize("role", ["admin", "admins", "manager", "editor", "viewer"])
    def test_a_retired_realm_role_grants_nothing(self, role: str) -> None:
        assert not self._allowed(_claims(roles=[role]), COMMUNITY_KEY)

    @pytest.mark.parametrize(
        "claims",
        [
            pytest.param(_claims(groups=["platform-admin", "/platform-admin"]), id="groups"),
            pytest.param({**_claims(), "roles": ["platform-admin"]}, id="top-roles"),
            pytest.param(
                _claims(resource_access={"oauth2_proxy": {"roles": ["platform-admin"]}}),
                id="client-role",
            ),
            pytest.param(
                _claims(organization={OTHER_REC: {"type": ["rec"], "groups": ["/platform-admin"]}}),
                id="org-group",
            ),
        ],
    )
    def test_platform_admin_counts_only_as_a_realm_role(self, claims: dict) -> None:
        assert not self._allowed(claims, COMMUNITY_KEY)

    def test_the_route_applies_the_same_rule(self, client, monkeypatch) -> None:
        test_client, app = client

        async def fake_list(pool, community_key, **kwargs):
            return {
                "community_key": community_key,
                "page": kwargs["page"],
                "page_size": kwargs["page_size"],
                "total": 0,
                "counts": {"new": 0, "seen": 0, "resolved": 0},
                "items": [],
            }

        import celine.roi.api.routes.feedback as feedback_routes

        monkeypatch.setattr(feedback_routes, "get_pool", lambda: object())
        monkeypatch.setattr(feedback_routes, "list_feedback", fake_list)

        def status(claims: dict, community_key: str) -> int:
            app.dependency_overrides[get_user_from_request] = lambda: _user_from_claims(claims)
            return test_client.get(f"/api/v1/feedback/manager/{community_key}").status_code

        assert status(PLATFORM_ADMIN, OTHER_REC) == 200
        assert status(ORG_ADMIN, COMMUNITY_KEY) == 200
        assert status(ORG_ADMIN, OTHER_REC) == 403
        assert status(LEGACY_REALM_ADMIN, COMMUNITY_KEY) == 403


class TestTheStoredAddressIsNotTheCallersChoice:
    """@verifies REQ-1301"""

    def test_x_forwarded_for_does_not_reach_the_row(self, client, monkeypatch) -> None:
        test_client, _ = client
        stored: dict = {}

        async def fake_save(pool, **kwargs):
            stored.update(kwargs)
            return {"id": FEEDBACK_ID, "created_at": datetime.now(UTC)}

        import celine.roi.api.routes.feedback as feedback_routes

        monkeypatch.setattr(feedback_routes, "get_pool", lambda: object())
        monkeypatch.setattr(feedback_routes, "save_feedback", fake_save)

        created = test_client.post(
            "/api/v1/feedback", json=_payload(), headers={"X-Forwarded-For": "198.51.100.1"}
        )

        assert created.status_code == 201
        assert stored["client_ip"] == "testclient"  # the TestClient's peer
