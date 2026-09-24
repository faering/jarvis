# Jarvis agent image. Built by docker-compose.yml (context: agent/).
# Two stages: resolve the locked env with uv, then copy only the venv into a slim runtime.

FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first (cached layer), then the project itself.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim
RUN useradd --system --uid 10001 --no-create-home jarvis
# State store (JARVIS_STATE_DB default /data/jarvis.db); a named volume inherits this owner.
RUN mkdir -p /data && chown jarvis /data
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER jarvis
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Build provenance from scripts/version.sh (see scripts/compose-build.sh). Last, so a new
# commit only rebuilds these metadata layers. Unset args never fail a build: GET /version
# then falls back to the package version and the labels read "unknown".
ARG VERSION=""
ARG REVISION=""
ARG BUILD_TIME=""
ENV JARVIS_VERSION="${VERSION}" \
    JARVIS_REVISION="${REVISION}" \
    JARVIS_BUILD_TIME="${BUILD_TIME}"
LABEL org.opencontainers.image.title="jarvis-agent" \
      org.opencontainers.image.source="https://github.com/faering/jarvis" \
      org.opencontainers.image.version="${VERSION:-unknown}" \
      org.opencontainers.image.revision="${REVISION:-unknown}" \
      org.opencontainers.image.created="${BUILD_TIME:-unknown}"
CMD ["uvicorn", "jarvis_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
