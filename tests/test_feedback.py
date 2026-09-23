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
