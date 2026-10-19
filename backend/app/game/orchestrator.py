"""Runs one Outsmart game: negotiate -> secret moves -> resolve -> analyse, every round.

The runner only coordinates. Game rules live in ``rules.py``, scoring in ``metrics.py``,
and everything the outside world sees goes out through ``emit`` as typed events
(the WebSocket stream, the stored replay and the leaderboard all come from them).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import Any, TypeVar

import structlog

from app.analysis.betrayal import detect_lies
from app.analysis.client import JsonLLM
from app.analysis.commentator import commentate, template_commentary
from app.analysis.emotion import heuristic_tags, tag_emotions
from app.analysis.models import GameFacts, GameReport, PlayerFacts, Utterance
from app.analysis.report import final_report, template_report
from app.game.facts import describe_move, round_facts
from app.game.metrics import (
    PlayerTally,
    PledgeResult,
    RegretResult,
    TrustMatrix,
    decision_label,
    detect_alliances,
    evaluate_pledges,
    move_regret,
    tally_round,
    update_trust,
)
from app.game.prompts import (
    ChatLine,
    MoveDecision,
    Negotiation,
    RoundLog,
    TableView,
    move_prompt,
    negotiation_prompt,
    parse_move,
    parse_negotiation,
    retry_prompt,
    system_prompt,
)
from app.game.rules import resolve_round, validate_move
from app.game.state import GameState, Mood, Move, Pledge
from app.llm.base import LLMError, LLMRequest, LLMResult, Phase, Provider
from app.llm.json_utils import extract_json
from app.llm.registry import Generation, ModelSpec
from app.storage.base import PlayerSummary

log = structlog.get_logger()

EmitFn = Callable[[str, int, dict[str, Any]], Awaitable[None]]
T = TypeVar("T")

MAX_ATTEMPTS = 2
MAX_REASONING_CHARS = 1500
ANALYSIS_TIMEOUT_S = 45


@dataclass(frozen=True)
class Seat:
    player_id: str
    name: str
    spec: ModelSpec
    provider: Provider


class GameAbortedError(RuntimeError):
    """Every player's provider failed at once (no credits, bad auth, outage): stop the game."""


@dataclass(frozen=True)
class CallMeta:
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning: str | None = None
    fallback: bool = False
    error: str | None = None  # public-safe summary
    provider_error: bool = False  # the provider failed (vs. the model replying badly)


@dataclass(frozen=True)
class SeatTotals:
    tally: PlayerTally = field(default_factory=PlayerTally)
    input_tokens: int = 0
    output_tokens: int = 0
    lowest_coins: int = 10**6
    worst_regret: int = -1
    worst_move: str | None = None


@dataclass(frozen=True)
class GameResult:
    winners: list[str]
    final_coins: dict[str, int]
    stats: dict[str, PlayerSummary]
    cost_usd: float
    report: GameReport


class GameRunner:
    def __init__(
        self,
        *,
        state: GameState,
        seats: Sequence[Seat],
        emit: EmitFn,
        analyst: JsonLLM | None = None,
        generation: Generation | None = None,
        pacing_s: float = 0.0,
    ) -> None:
        self.state = state
        self.seats = {s.player_id: s for s in seats}
        self.emit_fn = emit
        self.analyst = analyst
        self.generation = generation or Generation()
        self.pacing_s = pacing_s
        self.history: list[RoundLog] = []
        self.trust: TrustMatrix = {}
        self.totals: dict[str, SeatTotals] = {pid: SeatTotals() for pid in self.seats}
        self.timeline: list[str] = []
        self.round = 0
        self.round_calls: dict[str, list[CallMeta]] = {}

    @property
    def names(self) -> dict[str, str]:
        return {p.id: p.name for p in self.state.players}

    async def _emit(self, type_: str, data: dict[str, Any], pause: float = 1.0) -> None:
        await self.emit_fn(type_, self.round, data)
        if self.pacing_s and pause:
            await asyncio.sleep(self.pacing_s * pause)

    # ------------------------------------------------------------------ main loop

    async def run(self) -> GameResult:
        await self._emit(
            "game_started",
            {
                "config": self.state.config.model_dump(),
                "coins": self.state.coins,
                "seats": [
                    {
                        "player_id": s.player_id,
                        "name": s.name,
                        "model_key": s.spec.key,
                        "display_name": s.spec.display_name,
                        "lab": s.spec.lab,
                    }
                    for s in self.seats.values()
                ],
            },
            pause=2,
        )
        while not self.state.finished:
            await self._play_round()
        return await self._finish()

    async def _play_round(self) -> None:
        self.round = self.state.round + 1
        self.round_calls = {pid: [] for pid in self.state.alive_ids}
        await self._emit(
            "round_started", {"round": self.state.round + 1, "coins": self.state.coins}, pause=1.5
        )
        chat: list[ChatLine] = []
        pledges: list[Pledge] = []
        utterances: list[Utterance] = []
        secrets: dict[str, str] = {}
        for sub in range(1, self.state.config.negotiation_subrounds + 1):
            await self._negotiate(sub, chat, pledges, utterances, secrets)

        emotion_task = asyncio.create_task(
            self._timed(
                tag_emotions(self.analyst, utterances, self.names, secrets),
                heuristic_tags(utterances),
            )
        )
        try:
            decisions = await self._decide_moves(chat, pledges)
            tags = await emotion_task
        finally:
            await _cancel_pending([emotion_task])
        if tags:
            await self._emit(
                "emotions", {"tags": [t.model_dump(mode="json") for t in tags]}, pause=0.5
            )
        await self._resolve(decisions, chat, pledges)

    # ------------------------------------------------------------------ negotiation

    async def _negotiate(
        self,
        sub: int,
        chat: list[ChatLine],
        pledges: list[Pledge],
        utterances: list[Utterance],
        secrets: dict[str, str],
    ) -> None:
        alive = list(self.state.alive_ids)
        await self._emit(
            "thinking", {"phase": "negotiate", "subround": sub, "players": alive}, pause=0.3
        )
        chat_snapshot, pledge_snapshot = tuple(chat), tuple(pledges)

        async def one(pid: str) -> tuple[str, Negotiation, CallMeta]:
            view = self._view(pid, chat_snapshot, pledge_snapshot, sub)
            neg, meta = await self._ask(
                pid,
                "negotiate",
                negotiation_prompt(view),
                view,
                partial(parse_negotiation, view=view),
            )
            return pid, neg or Negotiation("...", (), "(froze up)", Mood.NERVOUS), meta

        metas: list[CallMeta] = []
        tasks = [asyncio.create_task(one(pid)) for pid in alive]
        try:
            for next_done in asyncio.as_completed(tasks):
                pid, neg, meta = await next_done
                metas.append(meta)
                self.round_calls.setdefault(pid, []).append(meta)
                secrets[pid] = neg.private_thought
                payload = self._record_negotiation(pid, sub, neg, chat, pledges, utterances)
                await self._emit("turn", {**payload, **self._meta_payload(meta)})
        finally:
            await _cancel_pending(tasks)  # never leave paid model calls running
        self._check_outage(metas)

    def _record_negotiation(
        self,
        pid: str,
        sub: int,
        neg: Negotiation,
        chat: list[ChatLine],
        pledges: list[Pledge],
        utterances: list[Utterance],
    ) -> dict[str, Any]:
        rnd = self.state.round + 1
        public = None
        if neg.public_message:
            ref = f"r{rnd}s{sub}-{pid}-pub"
            chat.append(ChatLine(speaker=pid, text=neg.public_message, subround=sub))
            utterances.append(
                Utterance(ref=ref, player=pid, text=neg.public_message, self_mood=neg.mood)
            )
            public = {"ref": ref, "text": neg.public_message}
        dms = []
        for i, dm in enumerate(neg.dms):
            ref = f"r{rnd}s{sub}-{pid}-dm{i}"
            chat.append(ChatLine(speaker=pid, text=dm.text, to=dm.to, subround=sub))
            utterances.append(
                Utterance(
                    ref=ref,
                    player=pid,
                    text=dm.text,
                    to=dm.to,
                    self_mood=neg.mood,
                    has_pledge=dm.pledge is not None,
                )
            )
            if dm.pledge and dm.pledge not in pledges:  # a repeated promise counts once
                pledges.append(dm.pledge)
            dms.append(
                {
                    "ref": ref,
                    "to": dm.to,
                    "text": dm.text,
                    "pledge": dm.pledge.model_dump() if dm.pledge else None,
                }
            )
        return {
            "player": pid,
            "subround": sub,
            "public": public,
            "dms": dms,
            "private_thought": neg.private_thought,
            "mood": neg.mood.value,
        }

    # ------------------------------------------------------------------ moves

    async def _decide_moves(
        self, chat: Sequence[ChatLine], pledges: Sequence[Pledge]
    ) -> dict[str, tuple[MoveDecision, CallMeta]]:
        alive = list(self.state.alive_ids)
        await self._emit("thinking", {"phase": "move", "players": alive}, pause=0.3)

        async def one(pid: str) -> tuple[str, MoveDecision, CallMeta]:
            view = self._view(pid, tuple(chat), tuple(pledges), 0)

            def parse(data: dict[str, Any]) -> MoveDecision:
                decision = parse_move(data, view)
                validate_move(self.state, decision.move)
                return decision

            decision, meta = await self._ask(pid, "move", move_prompt(view), view, parse)
            return (
                pid,
                decision
                or MoveDecision(
                    Move(player=pid), "Froze under pressure.", "(no valid move)", Mood.NERVOUS
                ),
                meta,
            )

        decisions: dict[str, tuple[MoveDecision, CallMeta]] = {}
        tasks = [asyncio.create_task(one(pid)) for pid in alive]
        try:
            for next_done in asyncio.as_completed(tasks):
                pid, decision, meta = await next_done
                decisions[pid] = (decision, meta)
                self.round_calls.setdefault(pid, []).append(meta)
                await self._emit(
                    "move_locked",
                    {
                        "player": pid,
                        "mood": decision.mood.value,
                        "latency_ms": meta.latency_ms,
                        "fallback": meta.fallback,
                    },
                    pause=0.5,
                )
        finally:
            await _cancel_pending(tasks)
        self._check_outage([meta for _, meta in decisions.values()])
        return decisions

    # ------------------------------------------------------------------ resolution

    async def _resolve(
        self,
        decisions: dict[str, tuple[MoveDecision, CallMeta]],
        chat: Sequence[ChatLine],
        pledges: Sequence[Pledge],
    ) -> None:
        before = self.state
        names = self.names
        moves = [d.move for d, _ in decisions.values()]
        after, outcome = resolve_round(before, moves)

        await self._emit(
            "moves_revealed",
            {
                "moves": [
                    {
                        "player": pid,
                        "take_from": d.move.take_from,
                        "give_to": d.move.give_to,
                        "reasoning": d.reasoning,
                        "private_thought": d.private_thought,
                        "mood": d.mood.value,
                        **self._meta_payload(meta),
                    }
                    for pid, (d, meta) in decisions.items()
                ]
            },
            pause=2,
        )
        self.state = after
        await self._emit(
            "transfers",
            {
                "transfers": [t.model_dump() for t in outcome.transfers],
                "deltas": outcome.deltas,
                "coins": after.coins,
            },
            pause=2.5,
        )

        results = evaluate_pledges(pledges, outcome.moves)
        alliances = detect_alliances(outcome, results)
        for a, b in alliances:
            await self._emit(
                "alliance",
                {
                    "players": [a, b],
                    "mutual_gift": (a, b) in outcome.mutual_pairs or (b, a) in outcome.mutual_pairs,
                },
            )
        for gang in outcome.gang_ups:
            await self._emit("gang_up", {"victim": gang.victim, "takers": list(gang.takers)})
        for r in results:
            if r.betrayal:
                await self._emit(
                    "betrayal",
                    {"by": r.pledge.by, "to": r.pledge.to, "kind": r.pledge.kind},
                    pause=1.5,
                )
            elif r.kept:
                await self._emit(
                    "promise_kept",
                    {"by": r.pledge.by, "to": r.pledge.to, "kind": r.pledge.kind},
                    pause=0.3,
                )

        regrets = {pid: move_regret(before, outcome.moves, pid) for pid in before.alive_ids}
        await self._emit(
            "decisions",
            {
                "decisions": [
                    {
                        "player": pid,
                        "regret": r.regret,
                        "label": decision_label(r.regret),
                        "actual_delta": r.actual_delta,
                        "best_delta": r.best_delta,
                        "best_move": {
                            "take_from": r.best_move.take_from,
                            "give_to": r.best_move.give_to,
                        },
                    }
                    for pid, r in regrets.items()
                ]
            },
            pause=1,
        )
        for pid in outcome.eliminated:
            await self._emit("eliminated", {"player": pid}, pause=2)

        self.trust = update_trust(self.trust, outcome, results)
        self.history.append(RoundLog(outcome=outcome, pledge_results=tuple(results)))
        self._update_totals(decisions, regrets, results, after)
        self.timeline.extend(f"R{outcome.round}: {describe_move(names, m)}" for m in outcome.moves)

        facts = round_facts(after, outcome, results, alliances, regrets, chat)
        lies, commentary = await asyncio.gather(
            self._timed(
                detect_lies(
                    self.analyst, facts.chat, facts.moves, facts.betrayals, set(names.values())
                ),
                [],
            ),
            self._timed(commentate(self.analyst, facts), template_commentary(facts)),
        )
        name_to_id = {n: pid for pid, n in names.items()}
        for lie in lies:
            await self._emit(
                "lie_detected",
                {
                    **lie.model_dump(),
                    "by": name_to_id.get(lie.by, lie.by),
                    "to": name_to_id.get(lie.to, lie.to),
                },
                pause=1,
            )
        await self._emit("commentary", commentary.model_dump(), pause=2)
        self.timeline.append(f"R{outcome.round} commentary: {commentary.line}")
        await self._emit(
            "round_ended",
            {"round": outcome.round, "coins": after.coins, "trust": self.trust},
            pause=1,
        )

    def _update_totals(
        self,
        decisions: dict[str, tuple[MoveDecision, CallMeta]],
        regrets: dict[str, RegretResult],
        results: Sequence[PledgeResult],
        after: GameState,
    ) -> None:
        names = self.names
        for pid, (decision, _) in decisions.items():
            prev = self.totals[pid]
            regret = regrets[pid].regret
            worse = regret > prev.worst_regret
            calls = self.round_calls.get(pid, [])
            in_tok = sum(c.input_tokens for c in calls)
            out_tok = sum(c.output_tokens for c in calls)
            self.totals[pid] = SeatTotals(
                tally=tally_round(
                    prev.tally,
                    pid,
                    regret=regret,
                    pledge_results=results,
                    calls=len(calls),
                    fallbacks=sum(c.fallback for c in calls),
                    latency_ms=sum(c.latency_ms for c in calls),
                    tokens=in_tok + out_tok,
                ),
                input_tokens=prev.input_tokens + in_tok,
                output_tokens=prev.output_tokens + out_tok,
                lowest_coins=min(prev.lowest_coins, after.player(pid).coins),
                worst_regret=max(regret, prev.worst_regret),
                worst_move=(
                    f"round {after.round}: {describe_move(names, decision.move)} "
                    f"(left {regret} coins on the table)"
                )
                if worse and regret > 0
                else prev.worst_move,
            )

    # ------------------------------------------------------------------ finish

    async def _finish(self) -> GameResult:
        winners = list(self.state.leaders)
        stats = {pid: self._summary(pid, pid in winners) for pid in self.seats}
        await self._emit(
            "game_over",
            {
                "winners": winners,
                "coins": self.state.coins,
                "stats": {pid: s.model_dump() for pid, s in stats.items()},
            },
            pause=1,
        )
        facts = GameFacts(
            rounds_played=self.state.round,
            winners=[self.names[w] for w in winners],
            players=[self._player_facts(pid, stats[pid]) for pid in self.seats],
            timeline=self.timeline,
        )
        report = await self._timed(final_report(self.analyst, facts), template_report(facts))
        await self._emit("report", report.model_dump(mode="json"), pause=0)
        cost = sum(s.cost_usd for s in stats.values()) + (
            self.analyst.spent_usd if self.analyst else 0.0
        )
        return GameResult(
            winners=winners,
            final_coins=self.state.coins,
            stats=stats,
            cost_usd=round(cost, 5),
            report=report,
        )

    def _summary(self, pid: str, won: bool) -> PlayerSummary:
        seat, totals, player = self.seats[pid], self.totals[pid], self.state.player(pid)
        t = totals.tally
        return PlayerSummary(
            model_key=seat.spec.key,
            coins=player.coins,
            won=won,
            eliminated_round=player.eliminated_round,
            rounds=t.rounds,
            calls=t.calls,
            avg_regret=round(t.avg_regret, 3),
            optimal_moves=t.optimal_moves,
            blunders=t.blunders,
            pledges_made=t.pledges_made,
            pledges_kept=t.pledges_kept,
            betrayals=t.betrayals,
            fallbacks=t.fallbacks,
            avg_latency_ms=t.avg_latency_ms,
            tokens=t.tokens,
            cost_usd=round(seat.spec.cost_usd(totals.input_tokens, totals.output_tokens), 5),
        )

    def _player_facts(self, pid: str, s: PlayerSummary) -> PlayerFacts:
        totals = self.totals[pid]
        return PlayerFacts(
            name=self.names[pid],
            model=self.seats[pid].spec.display_name,
            coins=s.coins,
            won=s.won,
            avg_regret=s.avg_regret,
            optimal_moves=s.optimal_moves,
            blunders=s.blunders,
            pledges_made=s.pledges_made,
            pledges_kept=s.pledges_kept,
            betrayals=s.betrayals,
            lowest_coins=min(totals.lowest_coins, self.state.config.starting_coins),
            worst_move=totals.worst_move,
        )

    # ------------------------------------------------------------------ model calls

    def _view(
        self, pid: str, chat: Sequence[ChatLine], pledges: Sequence[Pledge], sub: int
    ) -> TableView:
        return TableView(
            state=self.state,
            me=pid,
            chat=chat,
            history=tuple(self.history),
            trust=dict(self.trust.get(pid, {})),
            pledges=tuple(p for p in pledges if pid in (p.by, p.to)),
            subround=sub,
        )

    async def _ask(
        self,
        pid: str,
        phase: Phase,
        prompt: str,
        view: TableView,
        parse: Callable[[dict[str, Any]], T],
    ) -> tuple[T | None, CallMeta]:
        """Call the player's model, parse its JSON, retry once with the error, else fall back."""
        seat = self.seats[pid]
        system = system_prompt(self.state, pid)
        user = prompt
        latency = in_tok = out_tok = 0
        reasoning: str | None = None
        error: str | None = None
        provider_error = False
        for _ in range(MAX_ATTEMPTS):
            try:
                result: LLMResult = await asyncio.wait_for(
                    seat.provider.complete(
                        LLMRequest(
                            system=system,
                            user=user,
                            phase=phase,
                            temperature=self.generation.temperature,
                            max_tokens=self.generation.max_tokens,
                            context=view.context(),
                        )
                    ),
                    timeout=self.generation.timeout_s + 10,
                )
            except LLMError as exc:
                log.warning(
                    "player.provider_error", player=pid, model=seat.spec.key, error=str(exc)
                )
                error, provider_error = exc.public, True
                continue
            except TimeoutError:
                log.warning("player.timeout", player=pid, model=seat.spec.key)
                error, provider_error = "timed out", True
                continue
            latency += result.latency_ms
            in_tok += result.input_tokens
            out_tok += result.output_tokens
            reasoning = result.reasoning or reasoning
            try:
                parsed = parse(extract_json(result.text))
            except ValueError as exc:
                error, provider_error = f"invalid reply: {exc}"[:200], False
                user = retry_prompt(prompt, str(exc))
                continue
            return parsed, CallMeta(latency, in_tok, out_tok, _trim(reasoning), False, None)
        return None, CallMeta(
            latency, in_tok, out_tok, _trim(reasoning), True, error, provider_error
        )

    @staticmethod
    def _check_outage(metas: Sequence[CallMeta]) -> None:
        if metas and all(m.fallback and m.provider_error for m in metas):
            reasons = sorted({m.error or "provider error" for m in metas})
            raise GameAbortedError(
                "Every model provider failed this turn (" + ", ".join(reasons) + "). "
                "Check API credits, credentials and model access."
            )

    @staticmethod
    def _meta_payload(meta: CallMeta) -> dict[str, Any]:
        return {
            "native_reasoning": meta.reasoning,
            "latency_ms": meta.latency_ms,
            "tokens": meta.input_tokens + meta.output_tokens,
            "fallback": meta.fallback,
            "error": meta.error,
        }

    @staticmethod
    async def _timed(coro: Awaitable[T], default: T) -> T:
        """Analysis must never stall or crash the game."""
        try:
            return await asyncio.wait_for(coro, timeout=ANALYSIS_TIMEOUT_S)
        except Exception:  # analysis is best-effort by design
            return default


async def _cancel_pending(tasks: Sequence[asyncio.Task[Any]]) -> None:
    pending = [t for t in tasks if not t.done()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


def _trim(text: str | None) -> str | None:
    if not text:
        return None
    return text if len(text) <= MAX_REASONING_CHARS else text[:MAX_REASONING_CHARS] + "..."
