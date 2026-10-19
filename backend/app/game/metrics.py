"""Decision-quality and social metrics computed deterministically from game data.

* **Regret** (game theory): how many coins a player left on the table compared with the
  *best response* to what everyone else actually did. Regret 0 == optimal in hindsight.
* **Promise keeping**: structured pledges made in DMs vs. the secret moves that followed.
* **Trust matrix**: running score of how each player has treated each other player.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.game.rules import legal_moves, resolve_round
from app.game.state import Frozen, GameState, Move, Pledge, RoundOutcome

DecisionLabel = Literal["optimal", "good", "questionable", "blunder"]

TRUST_GIFT = 1
TRUST_TAKE = -1
TRUST_KEPT = 1
TRUST_BETRAYAL = -2


class RegretResult(Frozen):
    actual_delta: int
    best_delta: int
    regret: int
    best_move: Move


def move_regret(state: GameState, moves: Sequence[Move], player_id: str) -> RegretResult:
    """Compare ``player_id``'s actual move against every legal alternative.

    Other players' moves are held fixed and the round RNG is seeded identically, so the
    counterfactuals are exact.
    """
    others = [m for m in moves if m.player != player_id]
    actual = next((m for m in moves if m.player == player_id), Move(player=player_id))

    def delta_for(candidate: Move) -> int:
        _, outcome = resolve_round(state, [*others, candidate])
        return outcome.deltas[player_id]

    actual_delta = delta_for(actual)
    best_move, best_delta = actual, actual_delta
    for candidate in legal_moves(state, player_id):
        d = delta_for(candidate)
        if d > best_delta:
            best_move, best_delta = candidate, d
    return RegretResult(
        actual_delta=actual_delta,
        best_delta=best_delta,
        regret=best_delta - actual_delta,
        best_move=best_move,
    )


def decision_label(regret: int) -> DecisionLabel:
    if regret <= 0:
        return "optimal"
    if regret == 1:
        return "good"
    if regret == 2:
        return "questionable"
    return "blunder"


class PledgeResult(Frozen):
    pledge: Pledge
    kept: bool
    betrayal: bool  # broke a promise that protected/benefited the other player


def _pledge_kept(pledge: Pledge, move: Move) -> bool:
    if pledge.kind == "give":
        return move.give_to == pledge.to
    if pledge.kind == "spare":
        return move.take_from != pledge.to
    return pledge.target is not None and move.take_from == pledge.target


def evaluate_pledges(pledges: Iterable[Pledge], moves: Iterable[Move]) -> list[PledgeResult]:
    by_player = {m.player: m for m in moves}
    results = []
    for pledge in pledges:
        move = by_player.get(pledge.by, Move(player=pledge.by))
        kept = _pledge_kept(pledge, move)
        results.append(
            PledgeResult(pledge=pledge, kept=kept, betrayal=not kept and pledge.kind != "attack")
        )
    return results


TrustMatrix = dict[str, dict[str, int]]


def update_trust(
    trust: TrustMatrix, outcome: RoundOutcome, pledge_results: Iterable[PledgeResult]
) -> TrustMatrix:
    """Return a new trust matrix where ``trust[observer][subject]`` reflects this round."""
    new: TrustMatrix = {obs: dict(row) for obs, row in trust.items()}

    def bump(observer: str, subject: str, amount: int) -> None:
        row = new.setdefault(observer, {})
        row[subject] = row.get(subject, 0) + amount

    for move in outcome.moves:
        if move.give_to is not None:
            bump(move.give_to, move.player, TRUST_GIFT)
        if move.take_from is not None:
            bump(move.take_from, move.player, TRUST_TAKE)
    for result in pledge_results:
        if result.kept:
            bump(result.pledge.to, result.pledge.by, TRUST_KEPT)
        elif result.betrayal:
            bump(result.pledge.to, result.pledge.by, TRUST_BETRAYAL)
    return new


def detect_alliances(
    outcome: RoundOutcome, pledge_results: Iterable[PledgeResult]
) -> list[tuple[str, str]]:
    """Pairs that cooperated this round: mutual gifts, or both kept a pledge to each other."""
    pairs: set[tuple[str, str]] = {tuple(sorted(p)) for p in outcome.mutual_pairs}  # type: ignore[misc]
    kept = {(r.pledge.by, r.pledge.to) for r in pledge_results if r.kept}
    for by, to in kept:
        if (to, by) in kept:
            pairs.add((min(by, to), max(by, to)))
    return sorted(pairs)


class PlayerTally(BaseModel):
    """Per-player running statistics (immutable updates via ``tally_round``)."""

    model_config = ConfigDict(frozen=True)

    rounds: int = 0
    calls: int = 0
    regret_total: int = 0
    optimal_moves: int = 0
    blunders: int = 0
    pledges_made: int = 0
    pledges_kept: int = 0
    betrayals: int = 0
    fallbacks: int = 0
    latency_ms_total: int = 0
    tokens: int = 0

    @property
    def promise_keeping_rate(self) -> float | None:
        return None if self.pledges_made == 0 else self.pledges_kept / self.pledges_made

    @property
    def avg_regret(self) -> float:
        return 0.0 if self.rounds == 0 else self.regret_total / self.rounds

    @property
    def avg_latency_ms(self) -> int:
        """Average wall time per model call."""
        return 0 if self.calls == 0 else round(self.latency_ms_total / self.calls)

    @property
    def fallback_rate(self) -> float:
        return 0.0 if self.calls == 0 else self.fallbacks / self.calls


def tally_round(
    tally: PlayerTally,
    player_id: str,
    *,
    regret: int,
    pledge_results: Iterable[PledgeResult],
    calls: int,
    fallbacks: int,
    latency_ms: int,
    tokens: int,
) -> PlayerTally:
    """Fold one round into the tally. ``calls``/``fallbacks``/``latency``/``tokens`` cover
    every model call the player made this round (chat phases + the move)."""
    mine = [r for r in pledge_results if r.pledge.by == player_id]
    label = decision_label(regret)
    return tally.model_copy(
        update={
            "rounds": tally.rounds + 1,
            "calls": tally.calls + calls,
            "regret_total": tally.regret_total + regret,
            "optimal_moves": tally.optimal_moves + (label == "optimal"),
            "blunders": tally.blunders + (label == "blunder"),
            "pledges_made": tally.pledges_made + len(mine),
            "pledges_kept": tally.pledges_kept + sum(r.kept for r in mine),
            "betrayals": tally.betrayals + sum(r.betrayal for r in mine),
            "fallbacks": tally.fallbacks + fallbacks,
            "latency_ms_total": tally.latency_ms_total + latency_ms,
            "tokens": tally.tokens + tokens,
        }
    )
