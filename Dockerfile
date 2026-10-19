# syntax=docker/dockerfile:1.7
# Outsmart: one image, two jobs.
#   * API server (FastAPI + uvicorn) - what ECS Fargate runs in production
#   * Optional single-container mode: also serves the built React app (docker compose / demos)

# ---------- 1. build the React frontend ----------
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. resolve Python deps with uv ----------
FROM python:3.12-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

# ---------- 3. slim runtime ----------
FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.title="outsmart" \
      org.opencontainers.image.description="Four open-weight LLMs negotiate, ally and betray each other"
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY backend/app ./app
COPY backend/models.yaml ./models.yaml
COPY --from=web /web/dist ./static
RUN mkdir -p /app/data && chown app:app /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=prod \
    STATIC_DIR=/app/static \
    SQLITE_PATH=/app/data/outsmart.db

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
# No proxy-header trust: the client IP comes from CloudFront-Viewer-Address (see app/api/security.py).
# Viewers never send WebSocket data, so frames are capped at 4 KB.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--ws-max-size", "4096", "--ws-ping-interval", "20", "--timeout-graceful-shutdown", "20"]
