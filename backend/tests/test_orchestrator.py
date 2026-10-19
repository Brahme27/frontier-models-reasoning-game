import asyncio
import json
from collections import Counter
from typing import Any

import pytest

from app.config import BACKEND_DIR
from app.game.orchestrator import GameRunner, Seat
from app.game.rules import new_game
from app.game.state import GameConfig
from app.llm.base import LLMError, LLMRequest, LLMResult
from app.llm.fake import FakeProvider
from app.llm.registry import load_catalog

CATALOG = load_catalog(BACKEND_DIR / "models.yaml")
NAMES = ["Alex", "Blake", "Charlie", "Drew"]
PERSONAS = ["loyalist", "backstabber", "opportunist", "wildcard"]


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, int, dict[str, Any]]] = []

    async def __call__(self, type_: str, round_: int, data: dict[str, Any]) -> None:
        json.dumps(data)  # every payload must be JSON-serialisable for the wire
        self.events.append((type_, round_, data))

    def of(self, type_: str) -> list[dict[str, Any]]:
        return [d for t, _, d in self.events if t == type_]


def build_runner(
    providers: list[Any], analyst: Any = None, **cfg: Any
) -> tuple[GameRunner, Recorder]:
    specs = CATALOG.roster_specs()
    ids = [n.lower() for n in NAMES]
    state = new_game(
        GameConfig(seed=42, **cfg),
        [(i, n, s.key) for i, n, s in zip(ids, NAMES, specs, strict=True)],
    )
    seats = [
        Seat(player_id=i, name=n, spec=s, provider=p)
        for i, n, s, p in zip(ids, NAMES, specs, providers, strict=True)
    ]
    recorder = Recorder()
    return GameRunner(state=state, seats=seats, emit=recorder, analyst=analyst), recorder


def bots() -> list[FakeProvider]:
    return [
        FakeProvider(s.key, persona=p)
        for s, p in zip(CATALOG.roster_specs(), PERSONAS, strict=True)
    ]  # type: ignore[arg-type]


class TestFullGame:
    async def test_full_demo_game_runs_to_completion(self) -> None:
        runner, rec = build_runner(bots(), max_rounds=5)
        result = await runner.run()

        types = Counter(t for t, _, _ in rec.events)
        assert types["game_started"] == 1
        assert types["round_started"] == 5
        assert types["round_ended"] == 5
        assert types["moves_revealed"] == 5
        assert types["commentary"] == 5
        assert types["game_over"] == 1
        assert types["report"] == 1
        assert types["turn"] >= 5 * 2 * 3
        assert rec.events[-1][0] == "report"

        # the backstabber persona should actually betray someone in 5 rounds
        assert types["betrayal"] >= 1
        assert result.winners
        assert set(result.stats) == {"alex", "blake", "charlie", "drew"}
        assert sum(s.rounds for s in result.stats.values()) > 0
        assert result.report.awards

    async def test_event_rounds_are_consistent(self) -> None:
        runner, rec = build_runner(bots(), max_rounds=3)
        await runner.run()
        for type_, round_, data in rec.events:
            if type_ in {"round_started", "round_ended"}:
                assert data["round"] == round_
        assert {r for t, r, _ in rec.events if t == "moves_revealed"} == {1, 2, 3}

    async def test_turn_payload_shape(self) -> None:
        runner, rec = build_runner(bots(), max_rounds=1)
        await runner.run()
        turn = rec.of("turn")[0]
        assert {
            "player",
            "subround",
            "public",
            "dms",
            "private_thought",
            "mood",
            "native_reasoning",
            "latency_ms",
            "fallback",
        } <= turn.keys()
        decisions = rec.of("decisions")[0]["decisions"]
        assert all(d["label"] in {"optimal", "good", "questionable", "blunder"} for d in decisions)

    async def test_is_deterministic_for_same_seed(self) -> None:
        r1, _ = build_runner(bots(), max_rounds=3)
        r2, _ = build_runner(bots(), max_rounds=3)
        res1, res2 = await r1.run(), await r2.run()
        assert res1.final_coins == res2.final_coins


class BrokenProvider:
    label = "broken"

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls = 0

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        if self.mode == "error":
            raise LLMError("provider down")
        if self.mode == "garbage":
            return LLMResult(text="I refuse to output JSON", model="broken")
        if self.mode == "illegal":
            payload = (
                {"take_from": "Alex", "give_to": "Alex", "reasoning": "", "mood": "angry"}
                if request.phase == "move"
                else {"public_message": "hi", "dms": []}
            )
            return LLMResult(text=json.dumps(payload), model="broken")
        # "recover": garbage first, valid on retry
        if self.calls % 2 == 1:
            return LLMResult(text="oops", model="broken")
        payload = (
            {"take_from": "Blake", "give_to": None, "reasoning": "r", "mood": "smug"}
            if request.phase == "move"
            else {"public_message": "back!", "dms": []}
        )
        return LLMResult(text=json.dumps(payload), model="broken")


class TestResilience:
    @pytest.mark.parametrize("mode", ["error", "garbage", "illegal"])
    async def test_bad_provider_falls_back_and_game_continues(self, mode: str) -> None:
        broken = BrokenProvider(mode)
        providers: list[Any] = [broken, *bots()[1:]]
        runner, rec = build_runner(providers, max_rounds=2)
        result = await runner.run()
        assert result.stats["alex"].fallbacks >= 1
        alex_moves = [
            m for d in rec.of("moves_revealed") for m in d["moves"] if m["player"] == "alex"
        ]
        assert all(m["take_from"] is None and m["give_to"] is None for m in alex_moves)
        assert broken.calls >= 4  # retried each failed call

    async def test_retry_with_error_feedback_recovers(self) -> None:
        providers: list[Any] = [BrokenProvider("recover"), *bots()[1:]]
        runner, rec = build_runner(providers, max_rounds=1)
        result = await runner.run()
        assert result.stats["alex"].fallbacks == 0
        alex = next(m for m in rec.of("moves_revealed")[0]["moves"] if m["player"] == "alex")
        assert alex["take_from"] == "blake"


class StubAnalyst:
    """Pretends to be the analyst model, returning canned JSON per task."""

    def __init__(self) -> None:
        self.spent_usd = 0.01
        self.prompts: list[str] = []

    async def ask(self, system: str, user: str, max_tokens: int = 600) -> dict[str, Any] | None:
        self.prompts.append(system)
        if "body-language" in system:
            refs = [line.split(" | ")[0].removeprefix("ref=") for line in user.splitlines()]
            return {
                "tags": [
                    {
                        "ref": r,
                        "emotion": "scheming",
                        "intensity": 0.9,
                        "deception": 2.5,
                        "tone": "sweetly menacing",
                    }
                    for r in refs
                ]
            }
        if "referee" in system:
            return {
                "findings": [
                    {
                        "by": "Charlie",
                        "to": "Drew",
                        "quote": "trust me",
                        "explanation": "He did not mean it.",
                        "severity": "backstab",
                    },
                    {"by": "Nobody", "to": "Drew", "quote": "", "explanation": ""},
                ]
            }
        if "commentator" in system:
            return {"headline": "WOW", "line": "What a round!", "hype": "very"}
        if "professor" in system:
            return {
                "headline": "Big win",
                "summary": "It was close.",
                "awards": [
                    {
                        "title": "Most Loyal",
                        "emoji": "🤝",
                        "player": "Alex",
                        "reason": "kept promises",
                    }
                ],
                "decisions": [
                    {"player": "Blake", "round": 1, "verdict": "terrible", "explanation": "ouch"},
                    {
                        "player": "Blake",
                        "round": 1,
                        "verdict": "meh",
                        "explanation": "invalid verdict is skipped",
                    },
                ],
                "insights": [{"player": "Alex", "style": "loyal", "reasoning_quality": "ok"}],
            }
        return None


class TestWithAnalyst:
    async def test_analyst_outputs_flow_into_events(self) -> None:
        runner, rec = build_runner(bots(), analyst=StubAnalyst(), max_rounds=2)
        result = await runner.run()
        tags = rec.of("emotions")[0]["tags"]
        assert tags[0]["emotion"] == "scheming"
        assert tags[0]["deception"] == 1.0  # clamped
        lies = rec.of("lie_detected")
        assert lies and lies[0]["by"] == "charlie"  # names mapped back to ids
        assert all(lie["by"] != "Nobody" for lie in lies)
        commentary = rec.of("commentary")[0]
        assert commentary["line"] == "What a round!"
        report = rec.of("report")[0]
        assert report["generated_by"] == "llm"
        assert len(report["decisions"]) == 1
        assert result.cost_usd >= 0.01


async def test_move_rationale_is_not_overwritten_by_native_reasoning() -> None:
    runner, rec = build_runner(bots(), max_rounds=1)
    await runner.run()
    move = rec.of("moves_revealed")[0]["moves"][0]
    assert move["reasoning"]  # the model's one-line rationale
    assert move["native_reasoning"].startswith("[")  # FakeProvider's chain-of-thought


async def test_stats_include_negotiation_calls_and_tokens() -> None:
    runner, rec = build_runner(bots(), max_rounds=2)
    result = await runner.run()
    turn_tokens = sum(d["tokens"] for d in rec.of("turn") if d["player"] == "alex")
    move_tokens = sum(
        m["tokens"] for d in rec.of("moves_revealed") for m in d["moves"] if m["player"] == "alex"
    )
    assert result.stats["alex"].tokens == turn_tokens + move_tokens
    assert result.stats["alex"].calls == 6


class SlowProvider:
    label = "slow"

    def __init__(self) -> None:
        self.finished = 0

    async def complete(self, request: LLMRequest) -> LLMResult:
        await asyncio.sleep(5)
        self.finished += 1
        return LLMResult(text="{}", model="slow")


async def test_cancelling_a_game_cancels_in_flight_model_calls() -> None:
    slow = [SlowProvider() for _ in range(4)]
    runner, _ = build_runner(slow, max_rounds=1)  # type: ignore[arg-type]
    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.1)
    assert sum(p.finished for p in slow) == 0


class RepeatPledger:
    """Repeats the same promise in two DMs every chat phase."""

    label = "repeat"

    async def complete(self, request: LLMRequest) -> LLMResult:
        if request.phase == "negotiate":
            dm = {"to": "Blake", "message": "I won't touch you", "pledge": "spare", "target": None}
            return LLMResult(text=json.dumps({"public_message": "hi", "dms": [dm, dm]}), model="r")
        return LLMResult(text=json.dumps({"take_from": "Blake", "give_to": None}), model="r")


async def test_repeated_pledges_count_once() -> None:
    runner, rec = build_runner([RepeatPledger(), *bots()[1:]], max_rounds=1)
    result = await runner.run()
    assert len([b for b in rec.of("betrayal") if b["by"] == "alex"]) == 1
    assert result.stats["alex"].pledges_made == 1
