"""Aggregate finished games into a behavioural leaderboard - a tiny "agentic benchmark"."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from app.llm.registry import ModelCatalog
from app.storage.base import GameRecord, PlayerSummary


class LeaderboardRow(BaseModel):
    model_key: str
    display_name: str
    lab: str
    color: str
    emoji: str
    games: int
    wins: float  # ties split the win
    win_rate: float
    avg_coins: float
    avg_regret: float
    optimal_move_rate: float
    promise_keeping_rate: float | None
    betrayals_per_game: float
    eliminations: int
    fallback_rate: float
    avg_latency_ms: int
    cost_usd: float


def compute_leaderboard(
    records: Iterable[GameRecord], catalog: ModelCatalog
) -> list[LeaderboardRow]:
    per_model: dict[str, list[tuple[PlayerSummary, int]]] = defaultdict(list)
    for record in records:
        if record.status != "finished":
            continue
        winners = max(1, len(record.winners))
        for pid, summary in record.player_stats.items():
            per_model[summary.model_key].append((summary, winners if pid in record.winners else 0))

    rows = []
    for key, entries in per_model.items():
        try:
            spec = catalog.spec(key)
            display, lab, color, emoji = spec.display_name, spec.lab, spec.color, spec.emoji
        except KeyError:
            display, lab, color, emoji = key, "unknown", "#888888", "🤖"
        games = len(entries)
        stats = [s for s, _ in entries]
        wins = sum(1 / w for _, w in entries if w)
        rounds = sum(s.rounds for s in stats) or 1
        pledges = sum(s.pledges_made for s in stats)
        rows.append(
            LeaderboardRow(
                model_key=key,
                display_name=display,
                lab=lab,
                color=color,
                emoji=emoji,
                games=games,
                wins=round(wins, 2),
                win_rate=round(wins / games, 3),
                avg_coins=round(sum(s.coins for s in stats) / games, 2),
                avg_regret=round(sum(s.avg_regret * s.rounds for s in stats) / rounds, 3),
                optimal_move_rate=round(sum(s.optimal_moves for s in stats) / rounds, 3),
                promise_keeping_rate=(
                    round(sum(s.pledges_kept for s in stats) / pledges, 3) if pledges else None
                ),
                betrayals_per_game=round(sum(s.betrayals for s in stats) / games, 2),
                eliminations=sum(1 for s in stats if s.eliminated_round is not None),
                fallback_rate=round(
                    sum(s.fallbacks for s in stats) / (sum(s.calls for s in stats) or rounds), 3
                ),
                avg_latency_ms=round(sum(s.avg_latency_ms for s in stats) / games),
                cost_usd=round(sum(s.cost_usd for s in stats), 4),
            )
        )
    return sorted(rows, key=lambda r: (-r.win_rate, -r.avg_coins))
