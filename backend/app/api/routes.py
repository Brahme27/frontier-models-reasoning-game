"""REST + WebSocket endpoints."""

from __future__ import annotations

import contextlib
import re
import time
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, WebSocket, status
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from pydantic import BaseModel, Field

from app.api.security import ConnectionLimiter, client_ip, ensure_admin, limiter
from app.config import get_settings
from app.events.bus import EventBus
from app.llm.registry import ModelCatalog
from app.services.leaderboard import LeaderboardRow, compute_leaderboard
from app.services.manager import (
    CapacityError,
    DailyLimitError,
    GameManager,
    ProviderConfigError,
)
from app.storage.base import GameRecord, Repository

api = APIRouter(prefix="/api")
ws_router = APIRouter()

LEADERBOARD_WINDOW = 500
LEADERBOARD_TTL_S = 30
WS_TRY_LATER = 4429

GAME_ID = re.compile(r"^[a-f0-9]{12}$")
Passcode = Annotated[str | None, Header(alias="X-Admin-Passcode")]


class StartGameRequest(BaseModel):
    max_rounds: int | None = Field(default=None, ge=3, le=15)


class StartGameResponse(BaseModel):
    id: str


class GameDetail(BaseModel):
    game: GameRecord
    events: list[dict[str, Any]]
    live: bool


def manager(request: Request) -> GameManager:
    return request.app.state.manager  # type: ignore[no-any-return]


def repo(request: Request) -> Repository:
    return request.app.state.repo  # type: ignore[no-any-return]


def catalog(request: Request) -> ModelCatalog:
    return request.app.state.catalog  # type: ignore[no-any-return]


@api.get("/health")
async def health(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "backend": settings.effective_backend,
        "demo_mode": settings.demo_mode,
        "analysis": settings.analyst_enabled,
        "running_games": request.app.state.manager.running_count,
    }


@api.get("/models")
async def models(request: Request) -> dict[str, Any]:
    cat = catalog(request)
    return {
        "backend": request.app.state.settings.effective_backend,
        "generation": cat.generation.model_dump(),
        "seat_names": cat.seat_names,
        "players": [s.model_dump(mode="json", exclude={"extra"}) for s in cat.roster_specs()],
        "analyst": (
            cat.analyst.model_dump(mode="json", include={"display_name", "lab", "why"})
            if cat.analyst and request.app.state.settings.analyst_enabled
            else None
        ),
    }


@api.post("/auth/check", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().auth_rate_limit)
async def auth_check(request: Request, passcode: Passcode = None) -> None:
    ensure_admin(request, passcode)  # inside the limiter: wrong guesses are counted too


@api.post("/games", status_code=status.HTTP_201_CREATED, response_model=StartGameResponse)
@limiter.limit(lambda: get_settings().start_rate_limit)
async def start_game(
    request: Request, body: StartGameRequest | None = None, passcode: Passcode = None
) -> StartGameResponse:
    ensure_admin(request, passcode)
    try:
        record = await manager(request).start_game((body or StartGameRequest()).max_rounds)
    except CapacityError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except DailyLimitError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except ProviderConfigError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Model provider not configured: {exc}"
        ) from exc
    return StartGameResponse(id=record.id)


@api.get("/games", response_model=list[GameRecord])
async def list_games(
    request: Request, limit: int = Query(default=30, ge=1, le=100)
) -> list[GameRecord]:
    return await repo(request).list_games(limit)


@api.get("/games/{game_id}", response_model=GameDetail)
async def get_game(request: Request, game_id: str) -> GameDetail:
    record = await repo(request).get_game(game_id) if GAME_ID.match(game_id) else None
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    events = await repo(request).list_events(game_id)
    return GameDetail(
        game=record,
        events=[e.model_dump() for e in events],
        live=manager(request).is_running(game_id),
    )


@api.get("/leaderboard", response_model=list[LeaderboardRow])
async def leaderboard(request: Request) -> list[LeaderboardRow]:
    """Aggregates up to 500 games, so results are cached briefly per process."""
    cached: tuple[float, list[LeaderboardRow]] | None = getattr(
        request.app.state, "leaderboard_cache", None
    )
    if cached and time.monotonic() - cached[0] < LEADERBOARD_TTL_S:
        return cached[1]
    rows = compute_leaderboard(await repo(request).list_games(LEADERBOARD_WINDOW), catalog(request))
    request.app.state.leaderboard_cache = (time.monotonic(), rows)
    return rows


@ws_router.websocket("/ws/games/{game_id}")
async def stream_game(websocket: WebSocket, game_id: str) -> None:
    """Send the backlog, then live events, then ``stream_end``. Late joiners miss nothing."""
    app = websocket.app
    repository: Repository = app.state.repo
    bus: EventBus = app.state.bus
    mgr: GameManager = app.state.manager
    viewers: ConnectionLimiter = app.state.viewers
    client = client_ip(websocket)

    await websocket.accept()
    if not viewers.acquire(client):
        await websocket.close(code=WS_TRY_LATER, reason="too many viewers, try again soon")
        return
    try:
        if not GAME_ID.match(game_id) or await repository.get_game(game_id) is None:
            await websocket.close(code=4404, reason="game not found")
            return
        await _stream(websocket, game_id, repository, bus, mgr)
    except WebSocketDisconnect:
        return
    finally:
        viewers.release(client)
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(RuntimeError):
                await websocket.close()


async def _stream(
    websocket: WebSocket, game_id: str, repository: Repository, bus: EventBus, mgr: GameManager
) -> None:
    async with bus.subscribe(game_id) as queue:
        # Decide *before* reading the backlog: if the game was live when we subscribed, its
        # end-of-stream sentinel is guaranteed to reach our queue, so we drain until it does.
        was_running = mgr.is_running(game_id)
        last_seq = -1
        for past in await repository.list_events(game_id):
            await websocket.send_text(past.model_dump_json())
            last_seq = past.seq
        if was_running:
            while (event := await queue.get()) is not None:
                if event.seq > last_seq:
                    await websocket.send_text(event.model_dump_json())
                    last_seq = event.seq
        await websocket.send_json({"type": "stream_end", "game_id": game_id})
