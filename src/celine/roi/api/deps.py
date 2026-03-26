"""FastAPI dependency providers for the CELINE ROI API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request

from celine.roi.api.schemas import ConfigOverrides


def get_config(request: Request) -> dict[str, Any]:
    """Retrieve the application config dict loaded at startup.

    The config is populated once during the lifespan event in app.py and
    stored in the module-level _state dict. All route handlers that need
    config declare: config: ConfigDep
    """
    from celine.roi.api.app import get_app_config

    return get_app_config()


ConfigDep = Annotated[dict[str, Any], Depends(get_config)]


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
    for key, value in overrides.model_dump(exclude_none=True).items():
        effective[key] = value
    return effective
