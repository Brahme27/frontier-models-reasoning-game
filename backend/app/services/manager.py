"""Creates games, runs them in the background, persists + broadcasts their events."""

from __future__ import annotations

import asyncio
import contextlib
import random
import secrets
import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog

from app.analysis.client import JsonLLM, ProviderJson
from app.config import Settings
from app.events.bus import EventBus, GameEvent
from app.game.orchestrator import GameAbortedError, GameRunner, Seat
from app.game.rules import new_game
from app.game.state import GameConfig
from app.llm.base import Provider
from app.llm.registry import (
    Generation,
    ModelCatalog,
    ModelSpec,
    build_analyst_provider,
    build_provider,
)
from app.storage.base import GameRecord, Repository, SeatInfo

log = structlog.get_logger()

DAY_SECONDS = 86_400
ProviderFactory = Callable[[ModelSpec, Settings, Generation], Provider]


class CapacityError(RuntimeError):
    """Too many games running right now."""


class DailyLimitError(RuntimeError):
    """The daily game budget is used up."""


class ProviderConfigError(RuntimeError):
    """A seat's model provider is not configured (missing key, unknown model id)."""


class GameManager:
    def __init__(
        self,
        *,
        settings: Settings,
        catalog: ModelCatalog,
        repo: Repository,
        bus: EventBus,
        provider_factory: ProviderFactory = build_provider,
        analyst_factory: Callable[[], JsonLLM | None] | None = None,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.repo = repo
        self.bus = bus
        self.provider_factory = provider_factory
        self.analyst_factory = analyst_factory or self._default_analyst
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._seq: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def _default_analyst(self) -> JsonLLM | None:
        try:
            provider = build_analyst_provider(self.settings, self.catalog)
        except ValueError:
            log.warning("analyst.misconfigured_using_templates", exc_info=True)
            return None
        if provider is None:
            return None
        spec = self.catalog.analyst
        price = spec.pricing_per_m if spec and not self.settings.analyst_model else None
        return ProviderJson(
            provider,
            input_price_per_m=price.input if price else 0.0,
            output_price_per_m=price.output if price else 0.0,
            budget_usd=self.settings.analyst_budget_usd,
        )

    def is_running(self, game_id: str) -> bool:
        task = self._tasks.get(game_id)
        return task is not None and not task.done()

    @property
    def running_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    async def start_game(self, max_rounds: int | None = None) -> GameRecord:
        async with self._lock:
            if self.running_count >= self.settings.max_concurrent_games:
                raise CapacityError("too many games are running; try again in a few minutes")
            recent = await self.repo.count_games_since(time.time() - DAY_SECONDS)
            if recent >= self.settings.max_games_per_day:
                raise DailyLimitError("daily game limit reached; watch a replay instead")

            seed = secrets.randbelow(1_000_000_000)
            config = GameConfig(seed=seed, max_rounds=max_rounds or GameConfig().max_rounds)
            specs = self.catalog.roster_specs()
            random.Random(seed).shuffle(specs)  # random seating: no model owns "first seat"
            names = self.catalog.seat_names
            try:
                seats = [
                    Seat(
                        player_id=name.lower(),
                        name=name,
                        spec=spec,
                        provider=self.provider_factory(
                            spec, self.settings, self.catalog.generation
                        ),
                    )
                    for name, spec in zip(names, specs, strict=True)
                ]
            except ValueError as exc:
                raise ProviderConfigError(str(exc)) from exc
            state = new_game(config, [(s.player_id, s.name, s.spec.key) for s in seats])
            record = GameRecord(
                id=uuid.uuid4().hex[:12],
                created_at=time.time(),
                backend=self.settings.effective_backend,
                config=config,
                seats=[_seat_info(s) for s in seats],
            )
            await self.repo.save_game(record)
            runner = GameRunner(
                state=state,
                seats=seats,
                emit=self._emitter(record.id),
                analyst=self.analyst_factory(),
                generation=self.catalog.generation,
                pacing_s=self.settings.event_pacing_ms / 1000,
            )
            self._seq[record.id] = 0
            self._tasks[record.id] = asyncio.create_task(self._run(record, runner))
            log.info("game.started", game_id=record.id, backend=record.backend, seed=seed)
            return record

    def _emitter(self, game_id: str) -> Callable[[str, int, dict[str, Any]], Any]:
        async def emit(type_: str, round_: int, data: dict[str, Any]) -> None:
            seq = self._seq[game_id]
            self._seq[game_id] = seq + 1
            event = GameEvent(
                game_id=game_id, seq=seq, type=type_, round=round_, ts=time.time(), data=data
            )
            await self.repo.append_event(event)
            self.bus.publish(event)

        return emit

    async def _run(self, record: GameRecord, runner: GameRunner) -> None:
        try:
            result = await runner.run()
            finished = record.model_copy(
                update={
                    "status": "finished",
                    "finished_at": time.time(),
                    "winners": result.winners,
                    "final_coins": result.final_coins,
                    "player_stats": result.stats,
                    "cost_usd": result.cost_usd,
                    "headline": result.report.headline,
                }
            )
            await self.repo.save_game(finished)
            log.info(
                "game.finished", game_id=record.id, winners=result.winners, cost_usd=result.cost_usd
            )
        except GameAbortedError as exc:
            log.warning("game.aborted", game_id=record.id, reason=str(exc))
            await self._fail(record, str(exc))
        except asyncio.CancelledError:
            await self._fail(record, "game was cancelled (server shutting down)")
            raise
        except Exception as exc:
            log.exception("game.failed", game_id=record.id)
            await self._fail(record, f"game crashed: {type(exc).__name__}")
        finally:
            self.bus.close(record.id)
            self._seq.pop(record.id, None)

    async def _fail(self, record: GameRecord, message: str) -> None:
        # Save the status first and independently: if storage itself caused the crash, the
        # error event may fail too, but the game must never be left "running" forever.
        failed = record.model_copy(
            update={"status": "failed", "finished_at": time.time(), "error": message}
        )
        try:
            await self.repo.save_game(failed)
        except Exception:
            log.exception("game.fail_save_failed", game_id=record.id)
        with contextlib.suppress(Exception):
            await self._emitter(record.id)("error", 0, {"message": message})

    async def wait(self, game_id: str) -> None:
        task = self._tasks.get(game_id)
        if task:
            await asyncio.gather(task, return_exceptions=True)

    async def shutdown(self) -> None:
        tasks = [t for t in self._tasks.values() if not t.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _seat_info(seat: Seat) -> SeatInfo:
    spec = seat.spec
    provider_label = seat.provider.label
    return SeatInfo(
        player_id=seat.player_id,
        name=seat.name,
        model_key=spec.key,
        display_name=spec.display_name,
        lab=spec.lab,
        color=spec.color,
        emoji=spec.emoji,
        reasoning=spec.reasoning,
        provider=provider_label,
    )
