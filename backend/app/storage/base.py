"""Persistence models and the repository interface (repository pattern)."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.events.bus import GameEvent
from app.game.state import GameConfig

GameStatus = Literal["running", "finished", "failed"]


class SeatInfo(BaseModel):
    player_id: str
    name: str
    model_key: str
    display_name: str
    lab: str
    color: str
    emoji: str
    reasoning: str
    provider: str


class PlayerSummary(BaseModel):
    model_key: str
    coins: int
    won: bool
    eliminated_round: int | None = None
    rounds: int = 0
    calls: int = 0
    avg_regret: float = 0.0
    optimal_moves: int = 0
    blunders: int = 0
    pledges_made: int = 0
    pledges_kept: int = 0
    betrayals: int = 0
    fallbacks: int = 0
    avg_latency_ms: int = 0
    tokens: int = 0
    cost_usd: float = 0.0


class GameRecord(BaseModel):
    id: str
    status: GameStatus = "running"
    created_at: float
    finished_at: float | None = None
    backend: str
    config: GameConfig
    seats: list[SeatInfo]
    winners: list[str] = Field(default_factory=list)
    final_coins: dict[str, int] = Field(default_factory=dict)
    player_stats: dict[str, PlayerSummary] = Field(default_factory=dict)
    cost_usd: float = 0.0
    headline: str | None = None
    error: str | None = None

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class Repository(Protocol):
    async def init(self) -> None: ...

    async def close(self) -> None: ...

    async def save_game(self, record: GameRecord) -> None:
        """Insert or replace a game record."""
        ...

    async def get_game(self, game_id: str) -> GameRecord | None: ...

    async def list_games(self, limit: int = 50) -> list[GameRecord]:
        """Most recent first."""
        ...

    async def count_games_since(self, ts: float) -> int: ...

    async def append_event(self, event: GameEvent) -> None: ...

    async def list_events(self, game_id: str) -> list[GameEvent]:
        """Ordered by ``seq``."""
        ...


class MemoryRepository:
    """In-memory repository used by tests and throwaway demo runs."""

    def __init__(self) -> None:
        self.games: dict[str, GameRecord] = {}
        self.events: dict[str, list[GameEvent]] = {}

    async def init(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def save_game(self, record: GameRecord) -> None:
        self.games[record.id] = record

    async def get_game(self, game_id: str) -> GameRecord | None:
        return self.games.get(game_id)

    async def list_games(self, limit: int = 50) -> list[GameRecord]:
        return sorted(self.games.values(), key=lambda g: -g.created_at)[:limit]

    async def count_games_since(self, ts: float) -> int:
        return sum(1 for g in self.games.values() if g.created_at >= ts)

    async def append_event(self, event: GameEvent) -> None:
        self.events.setdefault(event.game_id, []).append(event)

    async def list_events(self, game_id: str) -> list[GameEvent]:
        return sorted(self.events.get(game_id, []), key=lambda e: e.seq)
