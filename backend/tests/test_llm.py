import json
from types import SimpleNamespace
from typing import Any

import openai
import pytest
from botocore.exceptions import ClientError

from app.config import BACKEND_DIR, Settings
from app.llm.base import LLMError, LLMRequest
from app.llm.bedrock import BedrockProvider
from app.llm.fake import FakeProvider, persona_for
from app.llm.openai_compat import OpenAICompatProvider
from app.llm.registry import build_provider, load_catalog

REQ = LLMRequest(system="sys", user="user", phase="move")


class FakeCompletions:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def chat_response(content: str, **message_fields: Any) -> Any:
    message = SimpleNamespace(content=content, model_extra={}, **message_fields)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


def compat(completions: FakeCompletions, **kwargs: Any) -> OpenAICompatProvider:
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAICompatProvider(
        backend="hf",
        model_id="org/model",
        base_url=None,
        api_key="k",
        client=client,
        **kwargs,  # type: ignore[arg-type]
    )


class TestOpenAICompat:
    async def test_returns_text_usage_and_reasoning_field(self) -> None:
        completions = FakeCompletions(chat_response('{"a": 1}', reasoning_content="plotting"))
        result = await compat(
            completions, extra_body={"reasoning_effort": "low"}, prompt_suffix=" /no_think"
        ).complete(REQ)
        assert result.text == '{"a": 1}'
        assert result.reasoning == "plotting"
        assert result.input_tokens == 11
        assert result.output_tokens == 7
        assert result.model == "hf:org/model"
        call = completions.calls[0]
        assert call["messages"][1]["content"] == "user /no_think"
        assert call["extra_body"] == {"reasoning_effort": "low"}

    async def test_inline_think_tags_become_reasoning(self) -> None:
        completions = FakeCompletions(chat_response('<think>hmm</think>{"a": 1}'))
        result = await compat(completions).complete(REQ)
        assert result.reasoning == "hmm"
        assert result.text == '{"a": 1}'

    async def test_sdk_errors_become_llm_errors(self) -> None:
        completions = FakeCompletions(error=openai.APIConnectionError(request=None))  # type: ignore[arg-type]
        with pytest.raises(LLMError):
            await compat(completions).complete(REQ)

    async def test_no_choices_is_an_error(self) -> None:
        completions = FakeCompletions(SimpleNamespace(choices=[], usage=None))
        with pytest.raises(LLMError):
            await compat(completions).complete(REQ)


class StubBedrock:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def converse_response(text: str, reasoning: str | None = None) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if reasoning:
        content.append({"reasoningContent": {"reasoningText": {"text": reasoning}}})
    content.append({"text": text})
    return {
        "output": {"message": {"content": content}},
        "usage": {"inputTokens": 20, "outputTokens": 5},
    }


def validation_error() -> ClientError:
    return ClientError({"Error": {"Code": "ValidationException", "Message": "bad"}}, "Converse")


class TestBedrock:
    async def test_parses_text_reasoning_and_usage(self) -> None:
        stub = StubBedrock([converse_response('{"x": 1}', "secret plan")])
        provider = BedrockProvider(
            model_id="openai.gpt-oss-20b-1:0",
            region="us-east-1",
            additional_fields={"reasoning_effort": "low"},
            client=stub,
        )
        result = await provider.complete(REQ)
        assert result.text == '{"x": 1}'
        assert result.reasoning == "secret plan"
        assert result.total_tokens == 25
        assert stub.calls[0]["additionalModelRequestFields"] == {"reasoning_effort": "low"}
        assert stub.calls[0]["system"] == [{"text": "sys"}]

    async def test_retries_without_extra_fields_on_validation_error(self) -> None:
        stub = StubBedrock([validation_error(), converse_response("{}")])
        provider = BedrockProvider(
            model_id="m",
            region="us-east-1",
            additional_fields={"reasoning_effort": "low"},
            client=stub,
        )
        await provider.complete(REQ)
        assert "additionalModelRequestFields" not in stub.calls[1]

    async def test_other_errors_raise_llm_error(self) -> None:
        throttled = ClientError({"Error": {"Code": "ThrottlingException"}}, "Converse")
        provider = BedrockProvider(
            model_id="m", region="us-east-1", client=StubBedrock([throttled])
        )
        with pytest.raises(LLMError, match="ThrottlingException"):
            await provider.complete(REQ)

    async def test_failed_retry_raises_llm_error(self) -> None:
        stub = StubBedrock([validation_error(), validation_error()])
        provider = BedrockProvider(
            model_id="m", region="us-east-1", additional_fields={"a": 1}, client=stub
        )
        with pytest.raises(LLMError):
            await provider.complete(REQ)


def ctx(me: str = "a", **overrides: Any) -> dict[str, Any]:
    base = {
        "me": me,
        "names": {"a": "Alex", "b": "Blake", "c": "Charlie", "d": "Drew"},
        "coins": {"a": 12, "b": 14, "c": 10, "d": 12},
        "alive": ["a", "b", "c", "d"],
        "round": 1,
        "max_rounds": 10,
        "subround": 1,
        "trust": {},
        "pledges_to_me": [],
        "my_pledges": [],
        "seed": 7,
    }
    return {**base, **overrides}


class TestFakeProvider:
    @pytest.mark.parametrize("persona", ["loyalist", "backstabber", "opportunist", "wildcard"])
    async def test_every_persona_speaks_valid_protocol(self, persona: str) -> None:
        bot = FakeProvider("m", persona=persona)  # type: ignore[arg-type]
        talk = json.loads(
            (
                await bot.complete(LLMRequest(system="", user="", phase="negotiate", context=ctx()))
            ).text
        )
        assert talk["public_message"]
        assert talk["mood"]
        for dm in talk["dms"]:
            assert dm["to"] in {"Blake", "Charlie", "Drew"}
        my_pledges = [
            {"to": "b", "kind": "attack", "target": "c"},
            {"to": "d", "kind": "give", "target": None},
        ]
        move = json.loads(
            (
                await bot.complete(
                    LLMRequest(
                        system="",
                        user="",
                        phase="move",
                        context=ctx(
                            my_pledges=my_pledges,
                            pledges_to_me=[{"by": "b", "kind": "give", "target": None}],
                        ),
                    )
                )
            ).text
        )
        assert move["take_from"] in {None, "Blake", "Charlie", "Drew"}
        assert move["give_to"] in {None, "Blake", "Charlie", "Drew"}
        assert move["take_from"] != move["give_to"] or move["take_from"] is None

    async def test_is_deterministic(self) -> None:
        bot = FakeProvider("m")
        req = LLMRequest(system="", user="", phase="move", context=ctx())
        assert (await bot.complete(req)).text == (await bot.complete(req)).text

    async def test_two_player_endgame(self) -> None:
        bot = FakeProvider("m", persona="wildcard")
        req = LLMRequest(system="", user="", phase="move", context=ctx(alive=["a", "b"]))
        move = json.loads((await bot.complete(req)).text)
        assert move["take_from"] == "Blake"

    def test_persona_is_stable(self) -> None:
        assert persona_for("gpt-oss-20b") == persona_for("gpt-oss-20b")

    async def test_analysis_phase_returns_empty(self) -> None:
        result = await FakeProvider("m").complete(LLMRequest(system="", user="", phase="analysis"))
        assert json.loads(result.text) == {}


class TestRegistry:
    def test_catalog_loads_four_distinct_labs(self) -> None:
        catalog = load_catalog(BACKEND_DIR / "models.yaml")
        specs = catalog.roster_specs()
        assert len(specs) == 4
        assert len({s.lab for s in specs}) == 4
        for spec in specs:
            assert {"bedrock", "ollama"} <= spec.ids.keys()
            assert "hf" in spec.ids or spec.fallback_backend is not None

    def test_unknown_model_raises(self) -> None:
        with pytest.raises(KeyError):
            load_catalog(BACKEND_DIR / "models.yaml").spec("nope")

    def test_cost_estimate(self) -> None:
        spec = load_catalog(BACKEND_DIR / "models.yaml").spec("gpt-oss-20b")
        assert spec.cost_usd(1_000_000, 0) == pytest.approx(0.07)

    def test_build_providers_for_each_backend(self) -> None:
        catalog = load_catalog(BACKEND_DIR / "models.yaml")
        spec = catalog.spec("qwen3-32b")
        assert isinstance(build_provider(spec, Settings(demo_mode=True)), FakeProvider)
        hf = build_provider(spec, Settings(inference_backend="hf", hf_token="t"))
        assert isinstance(hf, OpenAICompatProvider)
        assert hf.prompt_suffix == " /no_think"
        assert isinstance(
            build_provider(spec, Settings(inference_backend="bedrock")), BedrockProvider
        )
        assert isinstance(
            build_provider(spec, Settings(inference_backend="ollama")), OpenAICompatProvider
        )

    def test_hf_requires_token(self) -> None:
        spec = load_catalog(BACKEND_DIR / "models.yaml").spec("qwen3-32b")
        with pytest.raises(ValueError, match="HF_TOKEN"):
            build_provider(spec, Settings(inference_backend="hf", hf_token=None))

    def test_mismatched_roster_raises(self) -> None:
        catalog = load_catalog(BACKEND_DIR / "models.yaml")
        broken = catalog.model_copy(update={"seat_names": ["A"]})
        with pytest.raises(ValueError):
            broken.roster_specs()
