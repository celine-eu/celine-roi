"""Authenticated ROI feedback collection and REC-scoped manager review."""

from __future__ import annotations

import base64
import binascii
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response

from celine.roi.api.database import (
    get_feedback_item,
    get_feedback_screenshot,
    get_feedback_status,
    get_pool,
    list_feedback,
    save_feedback,
    update_feedback_status,
)
from celine.roi.api.deps import (
    UserDep,
    client_ip,
    rec_community_keys,
    require_rec_manager,
    require_rec_member,
)
from celine.roi.api.schemas import (
    FeedbackCommunitiesResponse,
    FeedbackCreateRequest,
    FeedbackCreateResponse,
    FeedbackItemResponse,
    FeedbackListResponse,
    FeedbackState,
    FeedbackStatusUpdate,
)

router = APIRouter()
_STATUS_ORDER = {"new": 0, "seen": 1, "resolved": 2}
_SAFE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _require_pool():
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="ROI feedback persistence is not configured")
    return pool


@router.get("/feedback/communities", response_model=FeedbackCommunitiesResponse)
async def feedback_communities(user: UserDep) -> FeedbackCommunitiesResponse:
    """Return only REC memberships the authenticated caller may attach feedback to."""
    return FeedbackCommunitiesResponse(communities=rec_community_keys(user))


@router.post("/feedback", response_model=FeedbackCreateResponse, status_code=201)
async def create_feedback(
    request: Request,
    body: FeedbackCreateRequest,
    user: UserDep,
) -> FeedbackCreateResponse:
    require_rec_member(user, body.community_key)
    pool = _require_pool()

    screenshot_bytes: bytes | None = None
    screenshot_mime_type: str | None = None
    if body.screenshot:
        try:
            screenshot_bytes = base64.b64decode(body.screenshot.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid screenshot payload") from exc
        screenshot_mime_type = body.screenshot.mime_type

    context = body.context.model_dump()
    context["extra"] = {**body.context.extra, "community_key": body.community_key}
    created = await save_feedback(
        pool,
        community_key=body.community_key,
        user_id=user.sub,
        rating=body.rating,
        comment=body.comment.strip() or None,
        context=context,
        screenshot_mime_type=screenshot_mime_type,
        screenshot_bytes=screenshot_bytes,
        client_ip=client_ip(request),
    )
    return FeedbackCreateResponse.model_validate(created)


@router.get(
    "/feedback/manager/{community_key}",
    response_model=FeedbackListResponse,
)
async def list_manager_feedback(
    community_key: str,
    user: UserDep,
    status: FeedbackState | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, alias="pageSize", ge=1, le=100),
) -> FeedbackListResponse:
    require_rec_manager(user, community_key)
    result = await list_feedback(
        _require_pool(),
        community_key,
        status=status,
        page=page,
        page_size=page_size,
    )
    return FeedbackListResponse.model_validate(result)


@router.get("/feedback/manager/{community_key}/{feedback_id}/screenshot")
async def manager_feedback_screenshot(
    community_key: str,
    feedback_id: UUID,
    user: UserDep,
) -> Response:
    require_rec_manager(user, community_key)
    screenshot = await get_feedback_screenshot(_require_pool(), community_key, feedback_id)
    if screenshot is None or screenshot["screenshot_bytes"] is None:
        raise HTTPException(status_code=404, detail="Feedback screenshot not found")
    mime_type = screenshot["screenshot_mime_type"]
    media_type = mime_type if mime_type in _SAFE_IMAGE_TYPES else "application/octet-stream"
    return Response(content=screenshot["screenshot_bytes"], media_type=media_type)


@router.patch(
    "/feedback/manager/{community_key}/{feedback_id}",
    response_model=FeedbackItemResponse,
)
async def update_manager_feedback_status(
    community_key: str,
    feedback_id: UUID,
    body: FeedbackStatusUpdate,
    user: UserDep,
) -> FeedbackItemResponse:
    require_rec_manager(user, community_key)
    pool = _require_pool()
    current = await get_feedback_status(pool, community_key, feedback_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Feedback not found in this REC")
    if _STATUS_ORDER[body.status] < _STATUS_ORDER[current]:
        raise HTTPException(status_code=409, detail="Feedback status cannot move backward")
    if body.status == current:
        item = await get_feedback_item(pool, community_key, feedback_id)
    else:
        item = await update_feedback_status(
            pool,
            community_key,
            feedback_id,
            status=body.status,
            actor_id=user.sub,
        )
    if item is None:
        latest = await get_feedback_status(pool, community_key, feedback_id)
        if latest is None:
            raise HTTPException(status_code=404, detail="Feedback not found in this REC")
        raise HTTPException(status_code=409, detail="Feedback status cannot move backward")
    return FeedbackItemResponse.model_validate(item)
