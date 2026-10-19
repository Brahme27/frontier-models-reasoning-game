from typing import Any

import pytest

from app.analysis.client import ProviderJson
from app.analysis.commentator import commentate, template_commentary
from app.analysis.emotion import tag_emotions
from app.analysis.models import RoundFacts, Utterance
from app.config import BACKEND_DIR, Settings
from app.game.state import Mood
from app.llm.base import LLMError, LLMRequest, LLMResult
from app.llm.registry import build_analyst_provider, load_catalog


class ScriptedProvider:
    label = "scripted"

    def __init__(self, text: str = "{}", error: Exception | None = None) -> None:
        self.text, self.error = text, error
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        if self.error:
            raise self.error
        return LLMResult(text=self.text, model="scripted", input_tokens=1_000_000)


class TestProviderJson:
    async def test_parses_json_and_tracks_spend(self) -> None:
        provider = ScriptedProvider('<think>hmm</think>Sure: {"line": "hi"}')
        llm = ProviderJson(provider, input_price_per_m=0.58)
        assert await llm.ask("sys", "u") == {"line": "hi"}
        assert llm.spent_usd == pytest.approx(0.58)
        assert provider.requests[0].phase == "analysis"
        assert "JSON" in provider.requests[0].system
        assert llm.label == "scripted"

    async def test_budget_guard_stops_calls(self) -> None:
        provider = ScriptedProvider('{"a": 1}')
        llm = ProviderJson(provider, input_price_per_m=0.58, budget_usd=0.1)
        await llm.ask("s", "u")
        assert await llm.ask("s", "u") is None
        assert len(provider.requests) == 1

    @pytest.mark.parametrize("text", ["not json", "[1, 2]", ""])
    async def test_bad_content_returns_none(self, text: str) -> None:
        assert await ProviderJson(ScriptedProvider(text)).ask("s", "u") is None

    async def test_provider_error_returns_none(self) -> None:
        provider = ScriptedProvider(error=LLMError("down", public="x"))
        assert await ProviderJson(provider).ask("s", "u") is None


class TestAnalystFactory:
    catalog = load_catalog(BACKEND_DIR / "models.yaml")

    def test_off_by_default_and_in_demo_mode(self) -> None:
        assert build_analyst_provider(Settings(), self.catalog) is None
        assert (
            build_analyst_provider(
                Settings(demo_mode=True, analyst_backend="bedrock"), self.catalog
            )
            is None
        )

    def test_bedrock_uses_the_neutral_judge(self) -> None:
        provider = build_analyst_provider(Settings(analyst_backend="bedrock"), self.catalog)
        assert provider is not None and provider.label == "bedrock:deepseek.v3-v1:0"
        assert self.catalog.analyst is not None
        assert self.catalog.analyst.lab not in {s.lab for s in self.catalog.roster_specs()}

    def test_openai_compatible_free_tier(self) -> None:
        provider = build_analyst_provider(
            Settings(analyst_backend="openai_compat", analyst_api_key="k"), self.catalog
        )
        assert provider is not None and provider.label == "analyst:gemini-2.5-flash"

    def test_openai_compatible_requires_key(self) -> None:
        with pytest.raises(ValueError, match="ANALYST_API_KEY"):
            build_analyst_provider(Settings(analyst_backend="openai_compat"), self.catalog)

    def test_model_override(self) -> None:
        provider = build_analyst_provider(
            Settings(analyst_backend="bedrock", analyst_model="amazon.nova-pro-v1:0"), self.catalog
        )
        assert provider is not None and provider.label == "bedrock:amazon.nova-pro-v1:0"

    def test_missing_model_raises(self) -> None:
        bare = self.catalog.model_copy(update={"analyst": None})
        with pytest.raises(ValueError, match="no analyst model"):
            build_analyst_provider(Settings(analyst_backend="bedrock"), bare)


def facts(**overrides: Any) -> RoundFacts:
    base: dict[str, Any] = dict(
        round=1,
        max_rounds=10,
        moves=["Alex took from Blake"],
        coins={"Alex": 13, "Blake": 11},
        deltas={"Alex": 1, "Blake": -1},
    )
    return RoundFacts(**{**base, **overrides})


class TestCommentaryTemplates:
    @pytest.mark.parametrize(
        ("overrides", "headline"),
        [
            ({"eliminated": ["Blake"]}, "KNOCKED OUT!"),
            ({"betrayals": [("Alex", "Blake")]}, "BACKSTAB!"),
            ({"gang_ups": [("Blake", ["Alex", "Drew"])]}, "DOGPILE!"),
            ({"alliances": [("Alex", "Drew")]}, "POWER COUPLE"),
            ({}, "CAGEY ROUND"),
        ],
    )
    def test_most_dramatic_event_wins(self, overrides: dict[str, Any], headline: str) -> None:
        assert template_commentary(facts(**overrides)).headline == headline

    async def test_llm_commentary_includes_all_facts(self) -> None:
        seen: list[str] = []

        class Spy:
            spent_usd = 0.0

            async def ask(self, system: str, user: str, max_tokens: int = 600) -> dict[str, Any]:
                seen.append(user)
                return {"headline": "H", "line": "L", "hype": 0.4}

        result = await commentate(
            Spy(),
            facts(
                betrayals=[("Alex", "Blake")],
                alliances=[("Alex", "Drew")],
                gang_ups=[("Blake", ["Alex", "Drew"])],
                eliminated=["Blake"],
                blunders=["Blake (passed)"],
                chat=['Alex (public): "hi"'],
            ),
        )
        assert result.line == "L"
        for needle in ("BETRAYALS", "Alliances", "Gang-ups", "ELIMINATED", "Blunders", "quotes"):
            assert needle in seen[0]

    async def test_llm_failure_falls_back(self) -> None:
        class Down:
            spent_usd = 0.0

            async def ask(self, *a: Any, **k: Any) -> None:
                return None

        assert (await commentate(Down(), facts())).headline == "CAGEY ROUND"


class TestEmotionFallbacks:
    async def test_without_llm_uses_self_reported_mood(self) -> None:
        u = Utterance(ref="r", player="alex", text="hi", self_mood=Mood.SMUG, has_pledge=True)
        tags = await tag_emotions(None, [u], {"alex": "Alex"}, {})
        assert tags[0].emotion == Mood.SMUG
        assert tags[0].deception > 0.15

    async def test_partial_llm_tags_keep_fallback_for_missing(self) -> None:
        class Partial:
            spent_usd = 0.0

            async def ask(self, *a: Any, **k: Any) -> dict[str, Any]:
                return {"tags": [{"ref": "a", "emotion": "angry", "intensity": "x"}]}

        us = [
            Utterance(ref=r, player="alex", text="t", self_mood=Mood.LOYAL, to="blake")
            for r in ("a", "b")
        ]
        tags = await tag_emotions(Partial(), us, {"alex": "Alex", "blake": "Blake"}, {})
        assert tags[0].emotion == Mood.ANGRY
        assert tags[0].intensity == 0.5  # unparseable -> default
        assert tags[1].emotion == Mood.LOYAL
