"""Game events and the in-process pub/sub bus that fans them out to WebSocket viewers."""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ConfigDict

SUBSCRIBER_QUEUE_SIZE = 2_000


class GameEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    game_id: str
    seq: int
    type: str
    round: int
    ts: float
    data: dict[str, Any]


class EventBus:
    """Single-process fan-out. Swap for Redis pub/sub to run several backend replicas."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[GameEvent | None]]] = defaultdict(set)

    def publish(self, event: GameEvent) -> None:
        for queue in list(self._subscribers.get(event.game_id, ())):
            with contextlib.suppress(asyncio.QueueFull):  # slow viewer: drop, they can replay
                queue.put_nowait(event)

    def close(self, game_id: str) -> None:
        """Signal end-of-stream to everyone watching ``game_id`` (even a full, slow queue)."""
        for queue in list(self._subscribers.get(game_id, ())):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()  # drop one event to make room for the sentinel
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    def subscriber_count(self, game_id: str) -> int:
        return len(self._subscribers.get(game_id, ()))

    @contextlib.asynccontextmanager
    async def subscribe(self, game_id: str) -> AsyncIterator[asyncio.Queue[GameEvent | None]]:
        queue: asyncio.Queue[GameEvent | None] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers[game_id].add(queue)
        try:
            yield queue
        finally:
            self._subscribers[game_id].discard(queue)
            if not self._subscribers[game_id]:
                del self._subscribers[game_id]
