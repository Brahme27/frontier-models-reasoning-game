"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import RequestResponseEndpoint

from app.api.routes import api, ws_router
from app.api.security import BodySizeLimit, ConnectionLimiter, limiter
from app.config import Settings, get_settings
from app.events.bus import EventBus
from app.llm.registry import load_catalog
from app.services.manager import GameManager
from app.storage import build_repository

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(level=settings.log_level.upper(), format="%(message)s")
    renderer = (
        structlog.processors.JSONRenderer()
        if settings.app_env == "prod"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            renderer,
        ],
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        repo = build_repository(settings)
        await repo.init()
        bus = EventBus()
        catalog = load_catalog(settings.models_file)
        app.state.settings = settings
        app.state.repo = repo
        app.state.bus = bus
        app.state.catalog = catalog
        app.state.manager = GameManager(settings=settings, catalog=catalog, repo=repo, bus=bus)
        app.state.viewers = ConnectionLimiter(
            settings.max_ws_connections, settings.max_ws_per_client
        )
        structlog.get_logger().info(
            "app.started", backend=settings.effective_backend, storage=settings.storage_backend
        )
        try:
            yield
        finally:
            await app.state.manager.shutdown()
            await repo.close()

    app = FastAPI(
        title="Outsmart API",
        version="1.0.0",
        description="Four open-weight LLMs negotiate, ally and betray each other.",
        lifespan=lifespan,
        # interactive docs are a dev convenience; production does not advertise its surface
        docs_url=None if settings.app_env == "prod" else "/api/docs",
        openapi_url=None if settings.app_env == "prod" else "/api/openapi.json",
        redoc_url=None,
    )
    app.state.limiter = limiter
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_body_bytes)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Admin-Passcode"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    app.include_router(api)
    app.include_router(ws_router)
    _mount_spa(app, settings.static_dir)
    return app


def _mount_spa(app: FastAPI, static_dir: Path | None) -> None:
    """Serve the built React app (single-container mode, e.g. docker compose)."""
    if static_dir is None or not (static_dir / "index.html").exists():
        return
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404, detail="not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / "index.html")


app = create_app()
