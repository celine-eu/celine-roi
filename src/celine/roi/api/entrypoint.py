"""Production entrypoint for the CELINE ROI API.

Reads CELINE_CONFIG_DIR from the environment (defaults to "config/")
and exposes a pre-built ASGI app for uvicorn.

Usage:
    CELINE_CONFIG_DIR=/etc/celine/config uvicorn celine.roi.api.entrypoint:app --port 8000
"""

from __future__ import annotations

import os

from celine.roi.api.app import create_app


def main():
    config_dir = os.environ.get("CELINE_CONFIG_DIR", "config")
    app = create_app(config_dir=config_dir)
    return app
