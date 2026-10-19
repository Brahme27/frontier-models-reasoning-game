"""Amazon Bedrock provider using the model-agnostic Converse API."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.llm.base import LLMError, LLMRequest, LLMResult
from app.llm.json_utils import split_reasoning

# boto3 is blocking. A dedicated pool keeps slow model calls from starving the default
# executor that DynamoDB writes (the live event stream) also use.
_EXECUTOR = ThreadPoolExecutor(max_workers=32, thread_name_prefix="bedrock")


class BedrockProvider:
    def __init__(
        self,
        *,
        model_id: str,
        region: str,
        additional_fields: dict[str, Any] | None = None,
        prompt_suffix: str = "",
        timeout_s: float = 90,
        client: Any = None,
    ) -> None:
        self.model_id = model_id
        self.additional_fields = additional_fields or {}
        self.prompt_suffix = prompt_suffix
        self.client = client or boto3.client(
            "bedrock-runtime",
            region_name=region,
            # attempts x read_timeout stays inside the orchestrator's per-call budget
            config=Config(
                read_timeout=max(10, timeout_s / 2),
                connect_timeout=5,
                retries={"total_max_attempts": 2, "mode": "standard"},
                max_pool_connections=32,
            ),
        )

    @property
    def label(self) -> str:
        return f"bedrock:{self.model_id}"

    async def complete(self, request: LLMRequest) -> LLMResult:
        started = time.perf_counter()
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(_EXECUTOR, self._converse, request)
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        for block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                text_parts.append(block["text"])
            reasoning = block.get("reasoningContent", {}).get("reasoningText", {}).get("text")
            if reasoning:
                reasoning_parts.append(reasoning)
        inline_reasoning, text = split_reasoning("".join(text_parts))
        usage = response.get("usage", {})
        return LLMResult(
            text=text,
            model=self.label,
            reasoning="\n".join(reasoning_parts).strip() or inline_reasoning,
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    def _converse(self, request: LLMRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": request.system}],
            "messages": [
                {"role": "user", "content": [{"text": request.user + self.prompt_suffix}]}
            ],
            "inferenceConfig": {
                "maxTokens": request.max_tokens,
                "temperature": request.temperature,
            },
        }
        if self.additional_fields:
            kwargs["additionalModelRequestFields"] = self.additional_fields
        try:
            result: dict[str, Any] = self.client.converse(**kwargs)
            return result
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            # Model-specific extras (e.g. reasoning_effort) are not universally accepted:
            # degrade gracefully instead of losing the player's turn.
            if code == "ValidationException" and "additionalModelRequestFields" in kwargs:
                kwargs.pop("additionalModelRequestFields")
                try:
                    retry: dict[str, Any] = self.client.converse(**kwargs)
                    return retry
                except (ClientError, BotoCoreError) as retry_exc:
                    raise LLMError(
                        f"{self.label} failed: {retry_exc}", public="bedrock ValidationException"
                    ) from retry_exc
            raise LLMError(
                f"{self.label} failed ({code}): {exc}", public=f"bedrock {code}"
            ) from exc
        except BotoCoreError as exc:
            raise LLMError(
                f"{self.label} failed: {exc}", public=f"bedrock {type(exc).__name__}"
            ) from exc
