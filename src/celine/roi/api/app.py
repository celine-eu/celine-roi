"""FastAPI application factory for the CELINE ROI API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from celine.roi.api.routes import energy, finance, incentives, production, scenario, validate
from celine.roi.config_loader import load_config

# Module-level state populated once per lifespan.
# Using a plain dict rather than app.state keeps get_app_config() testable
# without a live Request object.
_state: dict[str, Any] = {}


def get_app_config() -> dict[str, Any]:
    """Return the config dict loaded at startup. Used by deps.get_config."""
    return _state["config"]


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    config_dir = Path(app.state.config_dir)
    _state["config"] = load_config(config_dir)
    yield
    _state.clear()


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
    app = FastAPI(
        title="CELINE ROI API",
        description=(
            "Financial decision engine for Italian PV systems. "
            "Each pipeline phase is exposed as an independent endpoint so "
            "simulation layers can chain them autonomously and sweep parameters."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config_dir = str(config_dir)

    prefix = "/api/v1"
    app.include_router(production.router, prefix=prefix, tags=["production"])
    app.include_router(energy.router, prefix=prefix, tags=["energy"])
    app.include_router(incentives.router, prefix=prefix, tags=["incentives"])
    app.include_router(finance.router, prefix=prefix, tags=["finance"])
    app.include_router(validate.router, prefix=prefix, tags=["validate"])
    app.include_router(scenario.router, prefix=prefix, tags=["scenario"])

    return app
