"""OpenAI-compatible chat provider: Hugging Face Inference Providers, Ollama, or OpenAI."""

from __future__ import annotations

import time
from typing import Any

import openai
from openai import AsyncOpenAI

from app.llm.base import LLMError, LLMRequest, LLMResult
from app.llm.json_utils import split_reasoning


def _message_reasoning(message: Any) -> str | None:
    """Different servers expose chain-of-thought under different field names."""
    for attr in ("reasoning_content", "reasoning"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    extra = getattr(message, "model_extra", None) or {}
    for key in ("reasoning_content", "reasoning"):
        value = extra.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


class OpenAICompatProvider:
    def __init__(
        self,
        *,
        backend: str,
        model_id: str,
        base_url: str | None,
        api_key: str,
        extra_body: dict[str, Any] | None = None,
        prompt_suffix: str = "",
        timeout_s: float = 90,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.backend = backend
        self.model_id = model_id
        self.extra_body = extra_body or {}
        self.prompt_suffix = prompt_suffix
        self.client = client or AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=2
        )

    @property
    def label(self) -> str:
        return f"{self.backend}:{self.model_id}"

    async def complete(self, request: LLMRequest) -> LLMResult:
        started = time.perf_counter()
        try:
            response = await self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user + self.prompt_suffix},
                ],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                extra_body=self.extra_body or None,
            )
        except openai.APIStatusError as exc:
            raise LLMError(
                f"{self.label} failed: {exc}", public=f"{self.backend} HTTP {exc.status_code}"
            ) from exc
        except openai.OpenAIError as exc:
            raise LLMError(
                f"{self.label} failed: {exc}", public=f"{self.backend} {type(exc).__name__}"
            ) from exc

        if not response.choices:
            raise LLMError(f"{self.label} returned no choices", public="empty response")
        message = response.choices[0].message
        inline_reasoning, text = split_reasoning(message.content or "")
        usage = response.usage
        return LLMResult(
            text=text,
            model=self.label,
            reasoning=_message_reasoning(message) or inline_reasoning,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
