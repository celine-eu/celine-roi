"""FastAPI dependency providers for the CELINE ROI API."""

from __future__ import annotations

from typing import Annotated, Any

import jwt as pyjwt
from celine.sdk.auth import JwtUser, is_platform_admin, organization_groups
from fastapi import Depends, HTTPException, Request

from celine.roi.api.schemas import ConfigOverrides
from celine.roi.settings import settings


def _names(groups: list[str]) -> set[str]:
    return {group.strip("/").lower() for group in groups}


def extract_token(request: Request) -> str | None:
    token = request.headers.get(settings.jwt_header_name)
    if token:
        return token
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def get_user_from_request(request: Request) -> JwtUser:
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    try:
        return JwtUser.from_token(token, oidc=settings.oidc)
    except pyjwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token has expired") from exc
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Authentication failed") from exc


def rec_community_keys(user: JwtUser) -> list[str]:
    return sorted(
        org.alias
        for org in user.organizations
        if org.alias and (org.type or "").lower() == "rec"
    )


def require_rec_member(user: JwtUser, community_key: str) -> None:
    if community_key not in rec_community_keys(user):
        raise HTTPException(status_code=403, detail="REC membership required")


def require_rec_manager(user: JwtUser, community_key: str) -> None:
    claims = user.claims or {}
    raw_scope = claims.get("scope") or ""
    scopes = set(raw_scope.split() if isinstance(raw_scope, str) else raw_scope)
    if "community.read" not in scopes:
        raise HTTPException(status_code=403, detail="Missing community.read scope")
    # Platform-wide review is the realm role only (REQ-1105). A realm group in the
    # token grants nothing, and an organisation's groups count only for that REC.
    if is_platform_admin(claims):
        return
    organization = user.get_organization(community_key)
    groups = _names(organization_groups(claims, community_key))
    if (
        organization
        and (organization.type or "").lower() == "rec"
        and groups.intersection({"admins", "managers"})
    ):
        return
    raise HTTPException(status_code=403, detail="Manager access denied for this REC")


def get_config(request: Request) -> dict[str, Any]:
    """Retrieve the application config dict loaded at startup.

    The config is populated once during the lifespan event in app.py and
    stored in the module-level _state dict. All route handlers that need
    config declare: config: ConfigDep
    """
    from celine.roi.api.app import get_app_config

    return get_app_config()


ConfigDep = Annotated[dict[str, Any], Depends(get_config)]
UserDep = Annotated[JwtUser, Depends(get_user_from_request)]


def apply_config_overrides(
    base_config: dict[str, Any],
    overrides: ConfigOverrides,
) -> dict[str, Any]:
    """Merge per-request config overrides into a copy of the base config.

    Only fields explicitly set (not None) are applied.
    base_config is never mutated — a new dict is returned.

    Args:
        base_config: Server-loaded config dict from YAML files.
        overrides: ConfigOverrides instance from the request body.

    Returns:
        New dict with overrides applied.
    """
    effective = dict(base_config)
    overrides_dict = overrides.model_dump(exclude_none=True)
    for key, value in overrides_dict.items():
        effective[key] = value
    if "load_profile" in overrides_dict:
        effective.pop("load_profile_by_type", None)
    return effective
