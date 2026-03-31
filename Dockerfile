# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── builder ──────────────────────────────────────────────────────────────────
FROM base AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy manifests first for layer caching
COPY pyproject.toml README.md uv.lock ./

# Install dependencies only — cached unless lock changes
RUN uv sync --frozen --no-install-project --no-dev

# Copy application code and config
COPY src ./src
COPY config ./config

# Install the project itself into the venv
RUN uv pip install --no-deps .

# ── runtime ──────────────────────────────────────────────────────────────────
FROM base AS runtime

# Non-root user matching helm chart podSecurityContext.runAsUser: 1000
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --no-create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv  /app/.venv
COPY --from=builder --chown=app:app /app/src    /app/src
COPY --from=builder --chown=app:app /app/config /app/config

ENV PATH="/app/.venv/bin:${PATH}" \
    VIRTUAL_ENV="/app/.venv" \
    CELINE_CONFIG_DIR="/app/config"

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" \
    || exit 1

CMD ["uvicorn", "celine.roi.api.entrypoint:main", \
    "--factory", \
    "--host", "0.0.0.0", \
    "--port", "8000"]
