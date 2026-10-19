"""Human-readable summaries of game data (shared by analysts, prompts and reports)."""

from __future__ import annotations

from collections.abc import Sequence

from app.analysis.models import RoundFacts
from app.game.metrics import PledgeResult, RegretResult
from app.game.prompts import ChatLine
from app.game.state import GameState, Move, RoundOutcome


def describe_move(names: dict[str, str], move: Move) -> str:
    take = f"took from {names[move.take_from]}" if move.take_from else "took nothing"
    give = f"gave to {names[move.give_to]}" if move.give_to else "gave nothing"
    return f"{names[move.player]} {take}, {give}"


def chat_lines(names: dict[str, str], chat: Sequence[ChatLine]) -> list[str]:
    lines = []
    for c in chat:
        where = f"-> {names[c.to]} (private)" if c.to else "(public)"
        lines.append(f'{names[c.speaker]} {where}: "{c.text}"')
    return lines


def round_facts(
    state_after: GameState,
    outcome: RoundOutcome,
    pledge_results: Sequence[PledgeResult],
    alliances: Sequence[tuple[str, str]],
    regrets: dict[str, RegretResult],
    chat: Sequence[ChatLine],
) -> RoundFacts:
    names = {p.id: p.name for p in state_after.players}
    blunders = [
        f"{names[pid]} ({describe_move(names, next(m for m in outcome.moves if m.player == pid))};"
        f" best was: {describe_move(names, r.best_move)}, left {r.regret} coins on the table)"
        for pid, r in regrets.items()
        if r.regret >= 2
    ]
    return RoundFacts(
        round=outcome.round,
        max_rounds=state_after.config.max_rounds,
        moves=[describe_move(names, m) for m in outcome.moves],
        coins={names[pid]: c for pid, c in state_after.coins.items()},
        deltas={names[pid]: d for pid, d in outcome.deltas.items()},
        betrayals=[(names[r.pledge.by], names[r.pledge.to]) for r in pledge_results if r.betrayal],
        kept=[(names[r.pledge.by], names[r.pledge.to]) for r in pledge_results if r.kept],
        alliances=[(names[a], names[b]) for a, b in alliances],
        gang_ups=[(names[g.victim], [names[t] for t in g.takers]) for g in outcome.gang_ups],
        eliminated=[names[pid] for pid in outcome.eliminated],
        blunders=blunders,
        chat=chat_lines(names, chat),
    )
