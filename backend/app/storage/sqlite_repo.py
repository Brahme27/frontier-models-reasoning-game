"""SQLite repository for local development (zero setup)."""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from app.events.bus import GameEvent
from app.storage.base import GameRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    status TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS games_created ON games(created_at DESC);
CREATE TABLE IF NOT EXISTS events (
    game_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    doc TEXT NOT NULL,
    PRIMARY KEY (game_id, seq)
);
"""


class SqliteRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("repository not initialised; call init() first")
        return self._db

    async def init(self) -> None:
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def save_game(self, record: GameRecord) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO games (id, created_at, status, doc) VALUES (?, ?, ?, ?)",
            (record.id, record.created_at, record.status, json.dumps(record.to_doc())),
        )
        await self.db.commit()

    async def get_game(self, game_id: str) -> GameRecord | None:
        async with self.db.execute("SELECT doc FROM games WHERE id = ?", (game_id,)) as cur:
            row = await cur.fetchone()
        return GameRecord.model_validate_json(row[0]) if row else None

    async def list_games(self, limit: int = 50) -> list[GameRecord]:
        async with self.db.execute(
            "SELECT doc FROM games ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        return [GameRecord.model_validate_json(r[0]) for r in rows]

    async def count_games_since(self, ts: float) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM games WHERE created_at >= ?", (ts,)
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def append_event(self, event: GameEvent) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO events (game_id, seq, doc) VALUES (?, ?, ?)",
            (event.game_id, event.seq, event.model_dump_json()),
        )
        await self.db.commit()

    async def list_events(self, game_id: str) -> list[GameEvent]:
        async with self.db.execute(
            "SELECT doc FROM events WHERE game_id = ? ORDER BY seq", (game_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [GameEvent.model_validate_json(r[0]) for r in rows]
