"""FastAPI application factory for the CELINE ROI API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from celine.sdk.posture import docs_urls
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from celine.roi.api.limits import PublicLimitsMiddleware
from celine.roi.api.routes import (
    capex,
    compare,
    energy,
    estimates,
    feedback,
    finance,
    incentives,
    production,
    scenario,
    validate,
)
from celine.roi.config_loader import load_config
from celine.roi.posture import enforce_posture
from celine.roi.settings import settings

# Module-level state populated once per lifespan.
# Using a plain dict rather than app.state keeps get_app_config() testable
# without a live Request object.
_state: dict[str, Any] = {}

logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 3600


def get_app_config() -> dict[str, Any]:
    """Return the config dict loaded at startup. Used by deps.get_config."""
    return _state["config"]


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    config_dir = Path(app.state.config_dir)
    _state["config"] = load_config(config_dir)
    from celine.roi.api.database import close_pool, get_pool, init_pool

    await init_pool()
    purge = asyncio.create_task(_purge_client_ips()) if get_pool() is not None else None
    yield
    if purge is not None:
        purge.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await purge
    await close_pool()
    _state.clear()


async def _purge_client_ips() -> None:
    """Clear expired client addresses at startup and hourly after (REQ-1306)."""
    from celine.roi.api.database import get_pool, purge_client_ips

    while True:
        pool = get_pool()
        if pool is not None:
            try:
                estimates, feedback = await purge_client_ips(
                    pool, settings.client_ip_retention_days
                )
                if estimates or feedback:
                    logger.info(
                        "Cleared client_ip on %d estimates and %d feedback rows "
                        "older than %d days",
                        estimates,
                        feedback,
                        settings.client_ip_retention_days,
                    )
            except Exception:
                logger.exception("Failed to clear expired client addresses")
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)


def create_app(config_dir: str | Path = "config") -> FastAPI:
    """FastAPI application factory.

    Args:
        config_dir: Path to the directory containing YAML config files.
                    Defaults to "config/" relative to cwd (same default as CLI).

    Returns:
        Configured FastAPI application instance.

    Example:
        # Development
        uvicorn "celine.roi.api.app:create_app()" --factory --reload --port 8000

        # With custom config dir
        uvicorn "celine.roi.api.app:create_app('/etc/celine/config')" --factory --port 8000
    """
    # Refuse development defaults before the lifespan opens the database pool
    # (REQ-1201). Only CELINE_ENV=dev relaxes this; unset is hardened.
    enforce_posture(settings)

    app = FastAPI(
        title="CELINE ROI API",
        description=(
            "Financial decision engine for Italian PV systems. "
            "Each pipeline phase is exposed as an independent endpoint so "
            "simulation layers can chain them autonomously and sweep parameters."
        ),
        version="0.1.0",
        lifespan=lifespan,
        # Outside CELINE_ENV=dev none of /docs, /redoc, /openapi.json is mounted
        # unless CELINE_PUBLIC_DOCS=true (REQ-1201).
        **docs_urls(),
    )
    app.state.config_dir = str(config_dir)
    app.add_middleware(
        PublicLimitsMiddleware,
        calculators_per_minute=settings.rate_limit_calculators_per_minute,
        feedback_per_minute=settings.rate_limit_feedback_per_minute,
        calculators_max_body=settings.max_body_bytes_calculators,
        feedback_max_body=settings.max_body_bytes_feedback,
    )

    prefix = "/api/v1"
    app.include_router(production.router, prefix=prefix, tags=["production"])
    app.include_router(energy.router, prefix=prefix, tags=["energy"])
    app.include_router(incentives.router, prefix=prefix, tags=["incentives"])
    app.include_router(finance.router, prefix=prefix, tags=["finance"])
    app.include_router(validate.router, prefix=prefix, tags=["validate"])
    app.include_router(scenario.router, prefix=prefix, tags=["scenario"])
    app.include_router(capex.router, prefix=prefix, tags=["capex"])
    app.include_router(compare.router, prefix=prefix, tags=["compare"])
    app.include_router(estimates.router, prefix=prefix, tags=["estimates"])
    app.include_router(feedback.router, prefix=prefix, tags=["feedback"])

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Convert Pydantic validation errors to human-readable messages."""
        messages = []
        for err in exc.errors():
            field = " → ".join(str(loc) for loc in err["loc"] if loc != "body")
            messages.append(f"{field}: {err['msg']}")
        return JSONResponse(
            status_code=400,
            content={"detail": "; ".join(messages)},
        )

    return app
