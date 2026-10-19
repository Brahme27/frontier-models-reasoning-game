"""Inputs and outputs of the analyst (commentator, emotion tagger, lie detector, judge)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app.game.state import Mood


@dataclass(frozen=True)
class Utterance:
    ref: str
    player: str  # player id
    text: str
    self_mood: Mood
    to: str | None = None
    has_pledge: bool = False


@dataclass(frozen=True)
class RoundFacts:
    """Structured summary of one resolved round, keyed by player *names*."""

    round: int
    max_rounds: int
    moves: list[str]  # "Alex took from Blake, gave to Drew"
    coins: dict[str, int]
    deltas: dict[str, int]
    betrayals: list[tuple[str, str]] = field(default_factory=list)
    kept: list[tuple[str, str]] = field(default_factory=list)
    alliances: list[tuple[str, str]] = field(default_factory=list)
    gang_ups: list[tuple[str, list[str]]] = field(default_factory=list)
    eliminated: list[str] = field(default_factory=list)
    blunders: list[str] = field(default_factory=list)
    chat: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlayerFacts:
    name: str
    model: str
    coins: int
    won: bool
    avg_regret: float
    optimal_moves: int
    blunders: int
    pledges_made: int
    pledges_kept: int
    betrayals: int
    lowest_coins: int
    worst_move: str | None = None


@dataclass(frozen=True)
class GameFacts:
    rounds_played: int
    winners: list[str]
    players: list[PlayerFacts]
    timeline: list[str]


class EmotionTag(BaseModel):
    ref: str
    player: str
    emotion: Mood
    intensity: float = Field(ge=0, le=1)
    deception: float = Field(ge=0, le=1)
    tone: str


class LieFinding(BaseModel):
    by: str
    to: str
    quote: str
    explanation: str
    severity: Literal["white_lie", "lie", "backstab"] = "lie"


class Commentary(BaseModel):
    headline: str
    line: str
    hype: float = Field(default=0.5, ge=0, le=1)


class Award(BaseModel):
    title: str
    emoji: str
    player: str
    reason: str


class DecisionReview(BaseModel):
    player: str
    round: int
    verdict: Literal["brilliant", "good", "bad", "terrible"]
    explanation: str


class PlayerInsight(BaseModel):
    player: str
    style: str
    reasoning_quality: str


class GameReport(BaseModel):
    headline: str
    summary: str
    awards: list[Award] = Field(default_factory=list)
    decisions: list[DecisionReview] = Field(default_factory=list)
    insights: list[PlayerInsight] = Field(default_factory=list)
    generated_by: str = "template"
