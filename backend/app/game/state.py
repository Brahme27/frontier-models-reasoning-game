"""Immutable game-state models.

Every model is frozen: the engine never mutates state, it returns new copies.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Mood(StrEnum):
    """Shared emotion vocabulary used by players, analysts and the UI faces."""

    CONFIDENT = "confident"
    SCHEMING = "scheming"
    FRIENDLY = "friendly"
    SUSPICIOUS = "suspicious"
    BETRAYED = "betrayed"
    SMUG = "smug"
    DESPERATE = "desperate"
    ANGRY = "angry"
    NERVOUS = "nervous"
    GLEEFUL = "gleeful"
    LOYAL = "loyal"
    NEUTRAL = "neutral"

    @classmethod
    def parse(cls, value: object) -> Mood:
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.NEUTRAL


class GameConfig(Frozen):
    starting_coins: int = Field(default=12, ge=1, le=100)
    max_rounds: int = Field(default=10, ge=1, le=50)
    negotiation_subrounds: int = Field(default=2, ge=0, le=5)
    mutual_give_bonus: int = Field(default=1, ge=0, le=5)
    gang_up_bonus: int = Field(default=1, ge=0, le=5)
    max_dms_per_turn: int = Field(default=2, ge=0, le=3)
    seed: int = 0


class PlayerState(Frozen):
    id: str
    name: str
    model_key: str
    coins: int
    alive: bool = True
    eliminated_round: int | None = None


class Move(Frozen):
    """A player's secret move. ``None`` on either side means abstaining from that half."""

    player: str
    take_from: str | None = None
    give_to: str | None = None

    @property
    def is_pass(self) -> bool:
        return self.take_from is None and self.give_to is None


PledgeKind = Literal["give", "spare", "attack"]


class Pledge(Frozen):
    """A structured promise made in a DM.

    - give:   "I will give you a coin"
    - spare:  "I will not take from you"
    - attack: "I will take from <target>" (coordinated strike)
    """

    by: str
    to: str
    kind: PledgeKind
    target: str | None = None


TransferKind = Literal["take", "give", "mutual_bonus", "gang_bonus"]


class Transfer(Frozen):
    source: str | None  # None == the bank
    target: str
    amount: int
    kind: TransferKind


class GangUp(Frozen):
    victim: str
    takers: tuple[str, ...]


class RoundOutcome(Frozen):
    round: int
    moves: tuple[Move, ...]
    transfers: tuple[Transfer, ...]
    deltas: dict[str, int]
    mutual_pairs: tuple[tuple[str, str], ...]
    gang_ups: tuple[GangUp, ...]
    eliminated: tuple[str, ...]


class GameState(Frozen):
    config: GameConfig
    players: tuple[PlayerState, ...]
    round: int = 0
    finished: bool = False

    def player(self, player_id: str) -> PlayerState:
        for p in self.players:
            if p.id == player_id:
                return p
        raise KeyError(player_id)

    @property
    def alive_ids(self) -> tuple[str, ...]:
        return tuple(p.id for p in self.players if p.alive)

    @property
    def coins(self) -> dict[str, int]:
        return {p.id: p.coins for p in self.players}

    @property
    def leaders(self) -> tuple[str, ...]:
        """Players tied for the most coins (the winners once the game is over)."""
        top = max(p.coins for p in self.players)
        return tuple(p.id for p in self.players if p.coins == top)
