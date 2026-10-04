"""Manager review with real access tokens from the local development Keycloak.

These tests mint tokens on the local realm (the celine-dev stack, dev passwords equal to the
username) and send them to the application unchanged: the signature, issuer and audience are
verified by the same code path production uses, then `require_rec_manager` decides. Nothing
about the token is overridden.

They skip when the local Keycloak does not answer. Point them elsewhere with
`ROI_TEST_KEYCLOAK_TOKEN_URL`, but only at a local development realm: the users and the
client secret below are its development defaults.

A token that still carries the retired realm group `/admins` cannot be minted from a converged
realm, because no mapper writes a `groups` claim any more. Mint one with the platform's legacy
fixture and pass it in `ROI_TEST_LEGACY_REALM_GROUP_TOKEN`; without it that one test skips.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest
from fastapi.testclient import TestClient

from celine.roi.api.app import create_app
from celine.roi.settings import settings

TOKEN_URL = os.environ.get(
    "ROI_TEST_KEYCLOAK_TOKEN_URL",
    f"{settings.oidc.base_url}/protocol/openid-connect/token",
)
USER_CLIENT = os.environ.get("ROI_TEST_USER_CLIENT_ID", "oauth2_proxy")
USER_CLIENT_SECRET = os.environ.get("ROI_TEST_USER_CLIENT_SECRET", "oauth2_proxy")
LEGACY_TOKEN = os.environ.get("ROI_TEST_LEGACY_REALM_GROUP_TOKEN", "")

PLATFORM_ADMIN_USER = "admin"  # realm role platform-admin, plus org admins
ORG_ADMIN_USER = "org-admin"  # example_rec admins only
ORG_VIEWER_USER = "org-viewer"  # example_rec viewers only
COMMUNITY_KEY = "example_rec"
OTHER_REC = "another-rec"


def _mint(username: str) -> str | None:
    body = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": USER_CLIENT,
            "client_secret": USER_CLIENT_SECRET,
            "username": username,
            "password": username,
            "scope": "openid email profile organization:*",
        }
    ).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body), timeout=5) as r:
            return json.loads(r.read())["access_token"]
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        return None


def _claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


@pytest.fixture(scope="module")
def tokens() -> dict[str, str]:
    minted = {u: _mint(u) for u in (PLATFORM_ADMIN_USER, ORG_ADMIN_USER, ORG_VIEWER_USER)}
    if not all(minted.values()):
        pytest.skip(f"local Keycloak did not issue the dev users' tokens at {TOKEN_URL}")
    return minted  # type: ignore[return-value]


@pytest.fixture()
def api(monkeypatch):
    """The real app and real token verification; only the database is replaced."""
    import celine.roi.api.routes.feedback as feedback_routes

    async def fake_list(pool, community_key, **kwargs):
        return {
            "community_key": community_key,
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
            "total": 0,
            "counts": {"new": 0, "seen": 0, "resolved": 0},
            "items": [],
        }

    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(feedback_routes, "get_pool", lambda: object())
    monkeypatch.setattr(feedback_routes, "list_feedback", fake_list)
    with TestClient(create_app()) as client:

        def review(token: str, community_key: str) -> int:
            return client.get(
                f"/api/v1/feedback/manager/{community_key}",
                headers={settings.jwt_header_name: token},
            ).status_code

        yield review


class TestRealTokensFromTheLocalRealm:
    """@verifies REQ-1105"""

    def test_the_tokens_have_the_two_level_shape(self, tokens) -> None:
        admin = _claims(tokens[PLATFORM_ADMIN_USER])
        org_admin = _claims(tokens[ORG_ADMIN_USER])

        assert "platform-admin" in admin["realm_access"]["roles"]
        assert "platform-admin" not in org_admin.get("realm_access", {}).get("roles", [])
        assert org_admin["organization"][COMMUNITY_KEY]["groups"] == ["/admins"]
        assert "groups" not in admin and "groups" not in org_admin

    def test_a_platform_admin_reviews_every_rec(self, tokens, api) -> None:
        assert api(tokens[PLATFORM_ADMIN_USER], COMMUNITY_KEY) == 200
        assert api(tokens[PLATFORM_ADMIN_USER], OTHER_REC) == 200

    def test_an_organisation_admin_is_not_a_platform_admin(self, tokens, api) -> None:
        assert api(tokens[ORG_ADMIN_USER], COMMUNITY_KEY) == 200
        assert api(tokens[ORG_ADMIN_USER], OTHER_REC) == 403

    def test_an_organisation_viewer_reviews_nothing(self, tokens, api) -> None:
        assert api(tokens[ORG_VIEWER_USER], COMMUNITY_KEY) == 403

    def test_a_tampered_token_is_refused(self, tokens, api) -> None:
        header, _, signature = tokens[ORG_ADMIN_USER].split(".")
        forged = dict(_claims(tokens[ORG_ADMIN_USER]))
        forged["realm_access"] = {"roles": ["platform-admin"]}
        payload = base64.urlsafe_b64encode(json.dumps(forged).encode()).rstrip(b"=").decode()
        assert api(f"{header}.{payload}.{signature}", OTHER_REC) == 401

    @pytest.mark.skipif(not LEGACY_TOKEN, reason="ROI_TEST_LEGACY_REALM_GROUP_TOKEN not set")
    def test_a_legacy_realm_group_grants_nothing(self, api) -> None:
        claims = _claims(LEGACY_TOKEN)
        assert "/admins" in claims.get("groups", []) or "admins" in claims.get("groups", [])
        assert "platform-admin" not in claims.get("realm_access", {}).get("roles", [])
        assert api(LEGACY_TOKEN, COMMUNITY_KEY) == 403
        assert api(LEGACY_TOKEN, OTHER_REC) == 403
