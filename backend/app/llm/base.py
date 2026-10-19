"""Provider-agnostic LLM interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Phase = Literal["negotiate", "move", "analysis"]


class LLMError(RuntimeError):
    """Any failure talking to a model provider (network, auth, throttling, bad response).

    ``str(exc)`` holds full details for server logs; ``public`` is a short, safe summary
    (e.g. "HTTP 402") that may be shown to viewers - provider errors can contain account IDs.
    """

    def __init__(self, message: str, *, public: str = "provider error") -> None:
        super().__init__(message)
        self.public = public


@dataclass(frozen=True)
class LLMRequest:
    system: str
    user: str
    phase: Phase
    temperature: float = 0.7
    max_tokens: int = 3000
    # Structured view of the game; ignored by real models, used by the scripted FakeProvider.
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    reasoning: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class Provider(Protocol):
    @property
    def label(self) -> str:
        """Human readable "backend:model" string."""
        ...

    async def complete(self, request: LLMRequest) -> LLMResult: ...
