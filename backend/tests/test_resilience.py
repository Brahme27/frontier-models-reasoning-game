"""Provider fallbacks, total-outage aborts and public-safe error messages."""

import json
import time
from typing import Any

import httpx
import openai
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app.api.security import limiter
from app.config import BACKEND_DIR, Settings
from app.game.orchestrator import GameAbortedError
from app.llm.base import LLMError, LLMRequest, LLMResult
from app.llm.bedrock import BedrockProvider
from app.llm.openai_compat import OpenAICompatProvider
from app.llm.registry import build_provider, load_catalog
from app.main import create_app
from tests.test_llm import REQ, FakeCompletions, StubBedrock, compat
from tests.test_orchestrator import BrokenProvider, bots, build_runner

CATALOG = load_catalog(BACKEND_DIR / "models.yaml")
PASS = {"X-Admin-Passcode": "s3cret"}
ACCOUNT = "123456789012"


class TestFallbackBackend:
    def test_seat_without_hf_model_uses_its_fallback_backend(self) -> None:
        provider = build_provider(
            CATALOG.spec("magistral-small"),
            Settings(inference_backend="hf", hf_token="t", mistral_api_key="m"),
        )
        assert isinstance(provider, OpenAICompatProvider)
        assert provider.label == "mistral:magistral-small-2509"

    def test_fallback_backend_requires_its_key(self) -> None:
        with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
            build_provider(
                CATALOG.spec("magistral-small"), Settings(inference_backend="hf", hf_token="t")
            )

    def test_bedrock_uses_the_native_model(self) -> None:
        provider = build_provider(
            CATALOG.spec("magistral-small"), Settings(inference_backend="bedrock")
        )
        assert provider.label == "bedrock:mistral.magistral-small-2509"

    def test_missing_id_without_fallback_raises(self) -> None:
        broken = CATALOG.spec("qwen3-32b").model_copy(update={"ids": {"bedrock": "x"}})
        with pytest.raises(ValueError, match="no model id"):
            build_provider(broken, Settings(inference_backend="ollama"))


class TestPublicErrors:
    async def test_http_errors_expose_only_the_status_code(self) -> None:
        response = httpx.Response(
            402, request=httpx.Request("POST", "https://x"), json={"error": f"acct {ACCOUNT}"}
        )
        error = openai.APIStatusError(f"no credits for {ACCOUNT}", response=response, body=None)
        with pytest.raises(LLMError) as exc:
            await compat(FakeCompletions(error=error)).complete(REQ)
        assert exc.value.public == "hf HTTP 402"

    async def test_bedrock_errors_expose_only_the_error_code(self) -> None:
        denied = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": f"arn:aws:sts::{ACCOUNT}:x"}},
            "Converse",
        )
        provider = BedrockProvider(model_id="m", region="us-east-1", client=StubBedrock([denied]))
        with pytest.raises(LLMError) as exc:
            await provider.complete(REQ)
        assert exc.value.public == "bedrock AccessDeniedException"


class DownProvider:
    label = "down"

    async def complete(self, request: LLMRequest) -> LLMResult:
        raise LLMError(f"HTTP 402 for account {ACCOUNT}", public="hf HTTP 402")


class TestOutage:
    async def test_total_provider_outage_aborts_the_game(self) -> None:
        runner, rec = build_runner([DownProvider() for _ in range(4)], max_rounds=5)
        with pytest.raises(GameAbortedError, match="hf HTTP 402"):
            await runner.run()
        assert not rec.of("moves_revealed")  # stopped during the first chat phase
        assert all(ACCOUNT not in json.dumps(d) for _, _, d in rec.events)

    async def test_partial_outage_keeps_playing(self) -> None:
        runner, _ = build_runner([DownProvider(), *bots()[1:]], max_rounds=2)
        result = await runner.run()
        assert result.stats["alex"].fallbacks == 6  # 2 rounds x (2 chats + 1 move)
        assert result.stats["alex"].calls == 6

    async def test_bad_json_from_everyone_is_not_an_outage(self) -> None:
        runner, _ = build_runner([BrokenProvider("garbage") for _ in range(4)], max_rounds=1)
        result = await runner.run()
        assert all(s.fallbacks == 3 and s.calls == 3 for s in result.stats.values())


def api_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "app_env": "test",
        "demo_mode": True,
        "storage_backend": "memory",
        "event_pacing_ms": 0,
        "admin_passcode": "s3cret",
    }
    return Settings(**{**base, **overrides})


class TestApiFailures:
    def setup_method(self) -> None:
        limiter.reset()

    def test_missing_provider_key_returns_503(self) -> None:
        cfg = api_settings(demo_mode=False, inference_backend="hf", hf_token=None)
        with TestClient(create_app(cfg)) as c:
            response = c.post("/api/games", headers=PASS)
            assert response.status_code == 503
            assert "not configured" in response.json()["detail"]  # HF_TOKEN or MISTRAL_API_KEY

    def test_aborted_game_is_marked_failed_with_a_safe_reason(self) -> None:
        app = create_app(api_settings())
        with TestClient(app) as c:
            app.state.manager.provider_factory = lambda *a: DownProvider()
            game_id = c.post("/api/games", headers=PASS).json()["id"]
            deadline = time.time() + 20
            while time.time() < deadline:
                detail = c.get(f"/api/games/{game_id}").json()
                if detail["game"]["status"] != "running":
                    break
                time.sleep(0.05)
            assert detail["game"]["status"] == "failed"
            assert "HTTP 402" in detail["game"]["error"]
            assert ACCOUNT not in json.dumps(detail)
            assert detail["events"][-1]["type"] == "error"
