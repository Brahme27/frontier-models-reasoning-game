"""Model catalogue (``models.yaml``) and provider factory."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, SecretStr

from app.config import InferenceBackend, Settings
from app.llm.base import Provider
from app.llm.bedrock import BedrockProvider
from app.llm.fake import FakeProvider
from app.llm.openai_compat import OpenAICompatProvider


class Benchmarks(BaseModel):
    aa_index: float | None = None
    gpqa_diamond: float | None = None
    mmlu_pro: float | None = None
    arena_text: float | None = None


class Pricing(BaseModel):
    input: float
    output: float


class ModelSpec(BaseModel):
    key: str
    display_name: str
    lab: str
    color: str
    emoji: str = "🤖"
    params_total_b: float
    params_active_b: float
    architecture: str
    context_k: int
    license: str
    released: date
    reasoning: Literal["always", "hybrid", "none"]
    reasoning_note: str = ""
    prompt_suffix: str = ""
    provider: InferenceBackend | None = None
    # Used when the active backend does not host this model (e.g. no Mistral on the HF router).
    fallback_backend: InferenceBackend | None = None
    ids: dict[str, str]
    extra: dict[str, dict[str, Any]] = Field(default_factory=dict)
    benchmarks: Benchmarks = Field(default_factory=Benchmarks)
    pricing_per_m: Pricing | None = None

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        if self.pricing_per_m is None:
            return 0.0
        return (
            input_tokens * self.pricing_per_m.input + output_tokens * self.pricing_per_m.output
        ) / 1_000_000


class AnalystSpec(BaseModel):
    """The neutral judge: deliberately from a lab that has no player at the table."""

    display_name: str
    lab: str
    why: str = ""
    ids: dict[str, str]
    pricing_per_m: Pricing | None = None


class Generation(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 3000
    timeout_s: float = 90


class ModelCatalog(BaseModel):
    players: list[ModelSpec]
    alternates: list[ModelSpec] = Field(default_factory=list)
    seat_names: list[str]
    roster: list[str]
    generation: Generation = Field(default_factory=Generation)
    analyst: AnalystSpec | None = None

    def spec(self, key: str) -> ModelSpec:
        for spec in [*self.players, *self.alternates]:
            if spec.key == key:
                return spec
        raise KeyError(f"unknown model {key!r}")

    def roster_specs(self) -> list[ModelSpec]:
        if len(self.roster) != len(self.seat_names):
            raise ValueError("roster and seat_names must be the same length")
        return [self.spec(key) for key in self.roster]


def load_catalog(path: Path) -> ModelCatalog:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return ModelCatalog.model_validate(raw)


def _secret(value: SecretStr | None) -> str:
    return value.get_secret_value() if value else ""


def build_provider(
    spec: ModelSpec, settings: Settings, generation: Generation | None = None
) -> Provider:
    backend: InferenceBackend = (
        "fake" if settings.demo_mode else (spec.provider or settings.inference_backend)
    )
    if backend not in spec.ids and backend != "fake" and spec.fallback_backend:
        backend = spec.fallback_backend
    timeout = (generation or Generation()).timeout_s
    if backend == "fake":
        return FakeProvider(spec.key, latency_s=0.4 if settings.app_env != "test" else 0.0)

    model_id = spec.ids.get(backend)
    if not model_id:
        raise ValueError(f"{spec.key} has no model id for backend {backend!r}")
    extra = spec.extra.get(backend, {})

    if backend == "bedrock":
        return BedrockProvider(
            model_id=model_id,
            region=settings.aws_region,
            additional_fields=extra,
            prompt_suffix=spec.prompt_suffix,
            timeout_s=timeout,
        )
    if backend == "hf":
        if not _secret(settings.hf_token):
            raise ValueError("HF_TOKEN is required for the Hugging Face backend")
        return OpenAICompatProvider(
            backend="hf",
            model_id=model_id,
            base_url=settings.hf_base_url,
            api_key=_secret(settings.hf_token),
            extra_body=extra,
            prompt_suffix=spec.prompt_suffix,
            timeout_s=timeout,
        )
    if backend == "mistral":
        if not _secret(settings.mistral_api_key):
            raise ValueError("MISTRAL_API_KEY is required for the Mistral seat")
        return OpenAICompatProvider(
            backend="mistral",
            model_id=model_id,
            base_url=settings.mistral_base_url,
            api_key=_secret(settings.mistral_api_key),
            extra_body=extra,
            prompt_suffix=spec.prompt_suffix,
            timeout_s=timeout,
        )
    return OpenAICompatProvider(
        backend="ollama",
        model_id=model_id,
        base_url=settings.ollama_base_url,
        api_key="ollama",
        extra_body=extra,
        prompt_suffix=spec.prompt_suffix,
        timeout_s=timeout,
    )


def build_analyst_provider(settings: Settings, catalog: ModelCatalog) -> Provider | None:
    """The analyst's chat provider, or ``None`` when analysis is off (template commentary)."""
    if not settings.analyst_enabled:
        return None
    spec = catalog.analyst
    model_id = settings.analyst_model or (
        spec.ids.get(settings.analyst_backend, "") if spec else ""
    )
    if not model_id:
        raise ValueError(f"no analyst model configured for backend {settings.analyst_backend!r}")
    if settings.analyst_backend == "bedrock":
        return BedrockProvider(model_id=model_id, region=settings.aws_region, timeout_s=40)
    if not _secret(settings.analyst_api_key):
        raise ValueError("ANALYST_API_KEY is required for an OpenAI-compatible analyst")
    return OpenAICompatProvider(
        backend="analyst",
        model_id=model_id,
        base_url=settings.analyst_base_url,
        api_key=_secret(settings.analyst_api_key),
        timeout_s=40,
    )
