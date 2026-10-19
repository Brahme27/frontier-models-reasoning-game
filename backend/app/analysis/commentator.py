"""Sportscaster-style play-by-play for each round."""

from __future__ import annotations

from app.analysis.client import JsonLLM
from app.analysis.models import Commentary, RoundFacts

SYSTEM = """You are a hilarious, over-the-top sports commentator calling a live match of
OUTSMART, where four AI players negotiate, form alliances and betray each other for coins.
Given what happened this round, write ONE punchy headline (max 6 words, ALL CAPS allowed)
and ONE line of play-by-play commentary (max 30 words) full of personality, puns and drama.
Focus on the most dramatic event: betrayals > eliminations > gang-ups > alliances > blunders.
Reply as JSON: {"headline": "...", "line": "...", "hype": 0.0-1.0}"""


def _facts_text(f: RoundFacts) -> str:
    parts = [f"Round {f.round} of {f.max_rounds}.", "Moves: " + "; ".join(f.moves)]
    parts.append(
        "Coins now: " + ", ".join(f"{n} {c} ({f.deltas[n]:+d})" for n, c in f.coins.items())
    )
    if f.betrayals:
        parts.append(
            "BETRAYALS: " + ", ".join(f"{a} broke a promise to {b}" for a, b in f.betrayals)
        )
    if f.alliances:
        parts.append("Alliances: " + ", ".join(f"{a} & {b}" for a, b in f.alliances))
    if f.gang_ups:
        parts.append("Gang-ups: " + ", ".join(f"{' & '.join(t)} on {v}" for v, t in f.gang_ups))
    if f.eliminated:
        parts.append("ELIMINATED: " + ", ".join(f.eliminated))
    if f.blunders:
        parts.append("Blunders: " + ", ".join(f.blunders))
    if f.chat:
        parts.append("Notable quotes:\n" + "\n".join(f.chat[:6]))
    return "\n".join(parts)


def template_commentary(f: RoundFacts) -> Commentary:
    if f.eliminated:
        who = " and ".join(f.eliminated)
        return Commentary(
            headline="KNOCKED OUT!",
            line=f"{who} is out of coins and out of the game! Pour one out, folks.",
            hype=1.0,
        )
    if f.betrayals:
        a, b = f.betrayals[0]
        return Commentary(
            headline="BACKSTAB!",
            line=f"OH NO! {a} looked {b} right in the eye, "
            "made a promise... and broke it! Trust is officially bankrupt!",
            hype=0.95,
        )
    if f.gang_ups:
        victim, takers = f.gang_ups[0]
        return Commentary(
            headline="DOGPILE!",
            line=f"{' and '.join(takers)} team up on {victim}! "
            "That's a coordinated strike with a bonus on top!",
            hype=0.8,
        )
    if f.alliances:
        a, b = f.alliances[0]
        return Commentary(
            headline="POWER COUPLE",
            line=f"{a} and {b} are holding hands across "
            "the table. How long can this beautiful friendship last?",
            hype=0.6,
        )
    leader = max(f.coins, key=lambda n: f.coins[n])
    return Commentary(
        headline="CAGEY ROUND",
        line=f"Cautious play all around. {leader} leads "
        f"with {f.coins[leader]} coins as the tension builds.",
        hype=0.3,
    )


async def commentate(llm: JsonLLM | None, facts: RoundFacts) -> Commentary:
    fallback = template_commentary(facts)
    if llm is None:
        return fallback
    data = await llm.ask(SYSTEM, _facts_text(facts), max_tokens=200)
    if not data or not data.get("line"):
        return fallback
    try:
        hype = max(0.0, min(1.0, float(data.get("hype", fallback.hype))))
    except (TypeError, ValueError):
        hype = fallback.hype
    return Commentary(
        headline=str(data.get("headline") or fallback.headline)[:60],
        line=str(data["line"])[:280],
        hype=hype,
    )
