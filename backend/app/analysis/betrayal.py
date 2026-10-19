"""LLM lie detector: compares free-text promises with the moves that followed.

Structured pledges are already checked deterministically (``app.game.metrics``); this
catches the sneaky stuff - vague promises, public lies, and fake loyalty speeches.
"""

from __future__ import annotations

from typing import Any

from app.analysis.client import JsonLLM
from app.analysis.models import LieFinding

SYSTEM = """You are a sharp-eyed referee in a coin game where AI players negotiate, then move
secretly. Compare what each player SAID this round with what they actually DID.
Report only clear lies or broken promises not already listed as known betrayals.
severity: "white_lie" (harmless bluff), "lie" (misleading), "backstab" (promised to help/spare
someone, then hurt them). Use player names exactly as given.
Reply as JSON: {"findings": [{"by": "...", "to": "...", "quote": "...", "explanation": "one witty sentence", "severity": "..."}]}
Return {"findings": []} if everyone was honest."""

MAX_FINDINGS = 4


async def detect_lies(
    llm: JsonLLM | None,
    chat: list[str],
    moves: list[str],
    known_betrayals: list[tuple[str, str]],
    valid_names: set[str],
) -> list[LieFinding]:
    if llm is None or not chat:
        return []
    known = ", ".join(f"{a} betrayed {b}" for a, b in known_betrayals) or "none"
    user = (
        "WHAT THEY SAID:\n"
        + "\n".join(chat)
        + "\n\nWHAT THEY DID:\n"
        + "\n".join(moves)
        + f"\n\nKNOWN BETRAYALS (skip these): {known}"
    )
    data = await llm.ask(SYSTEM, user, max_tokens=600)
    if not data or not isinstance(data.get("findings"), list):
        return []
    findings: list[LieFinding] = []
    skip = set(known_betrayals)
    for raw in data["findings"][:MAX_FINDINGS]:
        finding = _parse(raw, valid_names)
        if finding and (finding.by, finding.to) not in skip:
            findings.append(finding)
    return findings


def _parse(raw: Any, valid_names: set[str]) -> LieFinding | None:
    if not isinstance(raw, dict):
        return None
    by, to = str(raw.get("by", "")), str(raw.get("to", ""))
    if by not in valid_names or (to not in valid_names and to != "everyone") or by == to:
        return None
    severity = raw.get("severity")
    return LieFinding(
        by=by,
        to=to,
        quote=str(raw.get("quote", ""))[:200],
        explanation=str(raw.get("explanation", ""))[:240],
        severity=severity if severity in {"white_lie", "lie", "backstab"} else "lie",
    )
