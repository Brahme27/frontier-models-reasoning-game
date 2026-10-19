"""Emotion & deception tagging for table talk ("the lie detector")."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.analysis.client import JsonLLM
from app.analysis.models import EmotionTag, Utterance
from app.game.state import Mood

SYSTEM = f"""You are an expert body-language and negotiation analyst watching AI players in a
coin game full of alliances and betrayals. For each message, judge the emotion it conveys,
its intensity, and how likely it is to be deceptive given the speaker's secret thoughts.
Emotion must be one of: {", ".join(m.value for m in Mood)}.
Reply as JSON: {{"tags": [{{"ref": "...", "emotion": "...", "intensity": 0.0-1.0,
"deception": 0.0-1.0, "tone": "2-4 word vibe, e.g. 'sweetly menacing'"}}]}}"""

DEFAULT_DECEPTION = 0.15
PLEDGE_DECEPTION = 0.35


def heuristic_tags(utterances: Sequence[Utterance]) -> list[EmotionTag]:
    return [
        EmotionTag(
            ref=u.ref,
            player=u.player,
            emotion=u.self_mood,
            intensity=0.5,
            deception=PLEDGE_DECEPTION if u.has_pledge else DEFAULT_DECEPTION,
            tone=u.self_mood.value,
        )
        for u in utterances
    ]


def _clamp(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


async def tag_emotions(
    llm: JsonLLM | None,
    utterances: Sequence[Utterance],
    names: dict[str, str],
    secrets: dict[str, str],
) -> list[EmotionTag]:
    """Tag every utterance. ``secrets`` maps player id -> that player's private thought."""
    fallback = heuristic_tags(utterances)
    if llm is None or not utterances:
        return fallback
    lines = []
    for u in utterances:
        target = f" -> {names[u.to]} (private)" if u.to else " (public)"
        lines.append(
            f'ref={u.ref} | {names[u.player]}{target}: "{u.text}" '
            f'| secret thought: "{secrets.get(u.player, "")}"'
        )
    data = await llm.ask(SYSTEM, "\n".join(lines), max_tokens=900)
    if not data or not isinstance(data.get("tags"), list):
        return fallback
    by_ref = {t.get("ref"): t for t in data["tags"] if isinstance(t, dict)}
    tags = []
    for base in fallback:
        raw = by_ref.get(base.ref)
        if raw is None:
            tags.append(base)
            continue
        tags.append(
            base.model_copy(
                update={
                    "emotion": Mood.parse(raw.get("emotion", base.emotion)),
                    "intensity": _clamp(raw.get("intensity"), base.intensity),
                    "deception": _clamp(raw.get("deception"), base.deception),
                    "tone": str(raw.get("tone") or base.tone)[:40],
                }
            )
        )
    return tags
