"""Provider-agnostic JSON client for the analyst (commentator, emotion tagger, judge).

The analyst runs on any ``Provider``: Amazon Bedrock in production (no extra API key, IAM
auth, fractions of a cent per game) or any OpenAI-compatible endpoint in development,
e.g. Google Gemini's free tier. Every call is best-effort with a per-game spend guard.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.llm.base import LLMError, LLMRequest, Provider
from app.llm.json_utils import extract_json

DEFAULT_BUDGET_USD = 0.25
JSON_ONLY = "\n\nReply with ONE valid JSON object and nothing else."


class JsonLLM(Protocol):
    spent_usd: float

    async def ask(self, system: str, user: str, max_tokens: int = 600) -> dict[str, Any] | None:
        """Return a parsed JSON object, or ``None`` on any failure (callers fall back)."""
        ...


class ProviderJson:
    """Turns any chat ``Provider`` into a budget-capped JSON answering machine."""

    def __init__(
        self,
        provider: Provider,
        *,
        input_price_per_m: float = 0.0,
        output_price_per_m: float = 0.0,
        budget_usd: float = DEFAULT_BUDGET_USD,
        temperature: float = 0.6,
    ) -> None:
        self.provider = provider
        self.input_price_per_m = input_price_per_m
        self.output_price_per_m = output_price_per_m
        self.budget_usd = budget_usd
        self.temperature = temperature
        self.spent_usd = 0.0

    @property
    def label(self) -> str:
        return self.provider.label

    async def ask(self, system: str, user: str, max_tokens: int = 600) -> dict[str, Any] | None:
        if self.spent_usd >= self.budget_usd:
            return None
        try:
            result = await self.provider.complete(
                LLMRequest(
                    system=system + JSON_ONLY,
                    user=user,
                    phase="analysis",
                    temperature=self.temperature,
                    # reasoning judges spend tokens thinking before they answer
                    max_tokens=max_tokens * 3,
                )
            )
        except LLMError:
            return None
        self.spent_usd += (
            result.input_tokens * self.input_price_per_m
            + result.output_tokens * self.output_price_per_m
        ) / 1_000_000
        try:
            return extract_json(result.text)
        except ValueError:
            return None
