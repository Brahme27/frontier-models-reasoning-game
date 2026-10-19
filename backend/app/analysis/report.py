"""Post-game analyst report: awards, good/bad decisions, and per-model playing styles."""

from __future__ import annotations

from typing import Any

from app.analysis.client import JsonLLM
from app.analysis.models import (
    Award,
    DecisionReview,
    GameFacts,
    GameReport,
    PlayerFacts,
    PlayerInsight,
)

SYSTEM = """You are a game-theory professor and witty sports analyst writing the post-match
report for OUTSMART, where four open-weight AI models negotiated, allied and betrayed each other.
Use the stats: "regret" = coins left on the table vs the best possible move (0 = optimal).
Write:
- headline (max 10 words) and a 3-4 sentence summary of how the game was won
- 4 awards: "Master Manipulator", "Most Loyal", "Biggest Blunder", "Best Strategist"
  (each with an emoji, the player name and a one-sentence reason)
- 3-5 key decisions (player, round, verdict brilliant|good|bad|terrible, one-sentence explanation)
- one insight per player: playing "style" (3-6 words) and "reasoning_quality" (one sentence)
Reply as JSON: {"headline": "...", "summary": "...", "awards": [{"title": "...", "emoji": "...", "player": "...", "reason": "..."}], "decisions": [{"player": "...", "round": 1, "verdict": "...", "explanation": "..."}], "insights": [{"player": "...", "style": "...", "reasoning_quality": "..."}]}"""


def _facts_text(facts: GameFacts) -> str:
    rows = []
    for p in facts.players:
        rate = f"{p.pledges_kept}/{p.pledges_made}" if p.pledges_made else "n/a"
        rows.append(
            f"- {p.name} ({p.model}): {p.coins} coins{' WINNER' if p.won else ''}, "
            f"avg regret {p.avg_regret:.2f}, optimal moves {p.optimal_moves}, blunders "
            f"{p.blunders}, promises kept {rate}, betrayals {p.betrayals}, lowest balance "
            f"{p.lowest_coins}, worst move: {p.worst_move or 'none'}"
        )
    return (
        f"Rounds played: {facts.rounds_played}. Winner(s): {', '.join(facts.winners)}.\n"
        "PLAYERS:\n" + "\n".join(rows) + "\n\nTIMELINE:\n" + "\n".join(facts.timeline[-40:])
    )


def _pick(players: list[PlayerFacts], key: Any) -> PlayerFacts:
    return max(players, key=key)


def template_report(facts: GameFacts) -> GameReport:
    players = facts.players
    winners = " & ".join(facts.winners)
    manipulator = _pick(players, lambda p: (p.betrayals, p.coins))
    loyal = _pick(
        players,
        lambda p: ((p.pledges_kept / p.pledges_made) if p.pledges_made else -1, p.pledges_kept),
    )
    blunder = _pick(players, lambda p: (p.blunders, p.avg_regret))
    strategist = min(players, key=lambda p: (p.avg_regret, -p.coins))
    awards = [
        Award(
            title="Master Manipulator",
            emoji="🐍",
            player=manipulator.name,
            reason=f"Broke {manipulator.betrayals} promise(s) without blinking.",
        ),
        Award(
            title="Most Loyal",
            emoji="🤝",
            player=loyal.name,
            reason=f"Kept {loyal.pledges_kept} of {loyal.pledges_made} promises.",
        ),
        Award(
            title="Biggest Blunder",
            emoji="🤡",
            player=blunder.name,
            reason=(f"{blunder.blunders} blunder(s). " if blunder.blunders else "")
            + f"Worst move: {blunder.worst_move or 'n/a'}.",
        ),
        Award(
            title="Best Strategist",
            emoji="♟️",
            player=strategist.name,
            reason=f"Lowest average regret ({strategist.avg_regret:.2f} coins per round).",
        ),
    ]
    insights = [
        PlayerInsight(
            player=p.name,
            style="backstabbing opportunist"
            if p.betrayals > 1
            else (
                "loyal team player" if p.pledges_kept >= max(1, p.pledges_made - 1) else "lone wolf"
            ),
            reasoning_quality=f"Optimal in {p.optimal_moves} of {facts.rounds_played} rounds.",
        )
        for p in players
    ]
    return GameReport(
        headline=f"{winners} {'outsmart' if len(facts.winners) > 1 else 'outsmarts'} the table!",
        summary=(
            f"After {facts.rounds_played} rounds of scheming, {winners} came out on top. "
            f"{manipulator.name} was the table's biggest snake, while {loyal.name} "
            "proved that some promises are worth keeping."
        ),
        awards=awards,
        insights=insights,
    )


def _parse(data: dict[str, Any], fallback: GameReport, names: set[str]) -> GameReport:
    awards = [
        Award.model_validate(a)
        for a in data.get("awards", [])
        if isinstance(a, dict) and a.get("player") in names
    ]
    decisions = []
    for d in data.get("decisions", []):
        if isinstance(d, dict) and d.get("player") in names:
            try:
                decisions.append(DecisionReview.model_validate(d))
            except ValueError:
                continue
    insights = [
        PlayerInsight.model_validate(i)
        for i in data.get("insights", [])
        if isinstance(i, dict) and i.get("player") in names
    ]
    return GameReport(
        headline=str(data.get("headline") or fallback.headline)[:120],
        summary=str(data.get("summary") or fallback.summary)[:1200],
        awards=awards or fallback.awards,
        decisions=decisions,
        insights=insights or fallback.insights,
        generated_by="llm",
    )


async def final_report(llm: JsonLLM | None, facts: GameFacts) -> GameReport:
    fallback = template_report(facts)
    if llm is None:
        return fallback
    data = await llm.ask(SYSTEM, _facts_text(facts), max_tokens=1500)
    if not data:
        return fallback
    try:
        return _parse(data, fallback, {p.name for p in facts.players})
    except ValueError:
        return fallback
