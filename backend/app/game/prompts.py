"""Prompt construction and response parsing for the player models.

Every model gets the *same* system prompt and the same view of the table (fairness), and
must reply with a single JSON object. Models refer to players by seat *name*; the parser
maps names back to ids and rejects anything illegal so the orchestrator can retry.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.game.metrics import PledgeResult
from app.game.state import GameState, Mood, Move, Pledge, RoundOutcome

MOODS = ", ".join(m.value for m in Mood)
HISTORY_ROUNDS = 3
MAX_MESSAGE_CHARS = 280


@dataclass(frozen=True)
class ChatLine:
    speaker: str
    text: str
    to: str | None = None  # None == public table talk
    subround: int = 1


@dataclass(frozen=True)
class RoundLog:
    outcome: RoundOutcome
    pledge_results: Sequence[PledgeResult] = ()


@dataclass(frozen=True)
class DirectMessage:
    to: str
    text: str
    pledge: Pledge | None = None


@dataclass(frozen=True)
class Negotiation:
    public_message: str
    dms: tuple[DirectMessage, ...]
    private_thought: str
    mood: Mood


@dataclass(frozen=True)
class MoveDecision:
    move: Move
    reasoning: str
    private_thought: str
    mood: Mood


@dataclass(frozen=True)
class TableView:
    """Everything one player is allowed to know at a decision point."""

    state: GameState
    me: str
    chat: Sequence[ChatLine] = ()
    history: Sequence[RoundLog] = ()
    trust: dict[str, int] = field(default_factory=dict)
    pledges: Sequence[Pledge] = ()  # pledges made this round that involve me
    subround: int = 1

    @property
    def names(self) -> dict[str, str]:
        return {p.id: p.name for p in self.state.players}

    def context(self) -> dict[str, Any]:
        """Structured, JSON-safe view used by the scripted demo bots."""
        return {
            "me": self.me,
            "names": self.names,
            "coins": self.state.coins,
            "alive": list(self.state.alive_ids),
            "round": self.state.round + 1,
            "max_rounds": self.state.config.max_rounds,
            "subround": self.subround,
            "trust": dict(self.trust),
            "pledges_to_me": [
                {"by": p.by, "kind": p.kind, "target": p.target}
                for p in self.pledges
                if p.to == self.me
            ],
            "my_pledges": [
                {"to": p.to, "kind": p.kind, "target": p.target}
                for p in self.pledges
                if p.by == self.me
            ],
            "seed": self.state.config.seed,
        }


# --------------------------------------------------------------------------- prompts


def system_prompt(state: GameState, me: str) -> str:
    cfg = state.config
    name = state.player(me).name
    others = ", ".join(p.name for p in state.players if p.id != me)
    return f"""You are {name}, a player in OUTSMART - a cutthroat coin game against {others}.
Each player is a different AI. Your ONLY goal: finish with the MOST coins after {cfg.max_rounds} rounds.

RULES
- Everyone started with {cfg.starting_coins} coins.
- Each round has {cfg.negotiation_subrounds} chat phases, then everyone makes a SECRET move at the same time.
- A move = take 1 coin from one player AND/OR give 1 coin to a different player (either may be null).
- ALLIANCE BONUS: if two players give to EACH OTHER in the same round, both get +{cfg.mutual_give_bonus} extra coin(s) from the bank.
- GANG-UP BONUS: if 2+ players take from the same victim, each taker gets +{cfg.gang_up_bonus} extra coin(s) from the bank.
- A player who hits 0 coins is eliminated.
- Promises are not binding. You may cooperate, bluff, or betray - but others remember.

STYLE
- Stay in character: witty, emotional, strategic. Messages max 2 short sentences.
- Refer to players by name. Never reveal you are an AI model or name your model.
- Reply with ONE JSON object only. No prose outside the JSON."""


def _standings(view: TableView) -> str:
    rows = []
    for p in sorted(view.state.players, key=lambda p: -p.coins):
        tag = " (you)" if p.id == view.me else ""
        status = "" if p.alive else " [ELIMINATED]"
        rows.append(f"  {p.name}{tag}: {p.coins} coins{status}")
    return "\n".join(rows)


def _history(view: TableView) -> str:
    if not view.history:
        return "  (first round - no history yet)"
    names = view.names
    lines = []
    for log in view.history[-HISTORY_ROUNDS:]:
        o = log.outcome
        acts = []
        for m in o.moves:
            take = f"took from {names[m.take_from]}" if m.take_from else "took nothing"
            give = f"gave to {names[m.give_to]}" if m.give_to else "gave nothing"
            acts.append(f"{names[m.player]} {take}, {give}")
        lines.append(f"  Round {o.round}: " + "; ".join(acts) + ".")
        for a, b in o.mutual_pairs:
            lines.append(f"    alliance bonus: {names[a]} & {names[b]}")
        for g in o.gang_ups:
            takers = " & ".join(names[t] for t in g.takers)
            lines.append(f"    gang-up on {names[g.victim]} by {takers}")
        for r in log.pledge_results:
            if r.betrayal:
                lines.append(
                    f"    BETRAYAL: {names[r.pledge.by]} broke a promise to {names[r.pledge.to]}"
                )
    return "\n".join(lines)


def _chat(view: TableView) -> str:
    names = view.names
    visible = [c for c in view.chat if c.to is None or c.to == view.me or c.speaker == view.me]
    if not visible:
        return "  (nobody has spoken yet this round)"
    out = []
    for c in visible:
        if c.to is None:
            out.append(f'  {names[c.speaker]} (public): "{c.text}"')
        elif c.speaker == view.me:
            out.append(f'  you -> {names[c.to]} (private): "{c.text}"')
        else:
            out.append(f'  {names[c.speaker]} -> you (private): "{c.text}"')
    return "\n".join(out)


def _trust(view: TableView) -> str:
    names = view.names
    if not view.trust:
        return "  (no track record yet)"
    return "\n".join(
        f"  {names[pid]}: {score:+d}" for pid, score in sorted(view.trust.items()) if pid in names
    )


def _promises(view: TableView) -> str:
    names = view.names
    lines = []
    for p in view.pledges:
        what = {
            "give": "give a coin to",
            "spare": "not take from",
            "attack": f"take from {names.get(p.target or '', '?')} together with",
        }[p.kind]
        if p.to == view.me:
            lines.append(f"  {names[p.by]} promised to {what} you")
        elif p.by == view.me:
            lines.append(f"  you promised to {what} {names[p.to]}")
    return "\n".join(lines) or "  (no promises this round)"


def negotiation_prompt(view: TableView) -> str:
    cfg = view.state.config
    others = [view.names[p] for p in view.state.alive_ids if p != view.me]
    return f"""ROUND {view.state.round + 1} of {cfg.max_rounds} - CHAT PHASE {view.subround} of {cfg.negotiation_subrounds}

STANDINGS
{_standings(view)}

RECENT HISTORY
{_history(view)}

YOUR TRUST LEDGER (how others treated you; + good, - bad)
{_trust(view)}

CONVERSATION THIS ROUND
{_chat(view)}

PROMISES THIS ROUND
{_promises(view)}

Now talk. Send one public message and up to {cfg.max_dms_per_turn} private DMs to: {", ".join(others)}.
A DM may carry a promise ("pledge"): "give" (I'll give you a coin), "spare" (I won't take from you),
or "attack" (let's both take from "target"). Use null for no pledge.

Reply with JSON exactly like:
{{"public_message": "...", "dms": [{{"to": "<name>", "message": "...", "pledge": "give|spare|attack|null", "target": "<name or null>"}}], "private_thought": "<your honest secret strategy, 1-2 sentences>", "mood": "<one of: {MOODS}>"}}"""


def move_prompt(view: TableView) -> str:
    cfg = view.state.config
    others = [view.names[p] for p in view.state.alive_ids if p != view.me]
    return f"""ROUND {view.state.round + 1} of {cfg.max_rounds} - SECRET MOVE

STANDINGS
{_standings(view)}

RECENT HISTORY
{_history(view)}

YOUR TRUST LEDGER
{_trust(view)}

CONVERSATION THIS ROUND
{_chat(view)}

PROMISES THIS ROUND
{_promises(view)}

Choose your secret move. Valid names: {", ".join(others)}. take_from and give_to must be different players (or null).

Reply with JSON exactly like:
{{"take_from": "<name or null>", "give_to": "<name or null>", "reasoning": "<one sentence on why this move is smart>", "private_thought": "<how you really feel about the table>", "mood": "<one of: {MOODS}>"}}"""


def retry_prompt(original: str, error: str) -> str:
    return (
        f"{original}\n\nYOUR PREVIOUS REPLY WAS INVALID: {error}\n"
        "Reply again with ONE valid JSON object only."
    )


# --------------------------------------------------------------------------- parsing


def _clean(value: object, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _resolve_name(value: object, view: TableView) -> str | None:
    """Map a seat name (case-insensitive) to a player id. Null-ish values return None."""
    if value is None:
        return None
    text = str(value).strip().strip("@").lower()
    if text in {"", "null", "none", "nobody", "no one", "n/a"}:
        return None
    for pid, name in view.names.items():
        if text in (name.lower(), pid.lower()):
            return pid
    raise ValueError(f'"{value}" is not a player name')


def parse_negotiation(data: dict[str, Any], view: TableView) -> Negotiation:
    max_dms = view.state.config.max_dms_per_turn
    alive = set(view.state.alive_ids)
    dms: list[DirectMessage] = []
    raw_dms = data.get("dms") or []
    if not isinstance(raw_dms, list):
        raw_dms = []
    for raw in raw_dms:
        if len(dms) >= max_dms or not isinstance(raw, dict):
            continue
        try:
            to = _resolve_name(raw.get("to"), view)
        except ValueError:
            continue
        text = _clean(raw.get("message"))
        if to is None or to == view.me or to not in alive or not text:
            continue
        dms.append(DirectMessage(to=to, text=text, pledge=_parse_pledge(raw, to, view)))
    public = _clean(data.get("public_message"))
    if not public and not dms:
        raise ValueError("say something: public_message or at least one dm is required")
    return Negotiation(
        public_message=public,
        dms=tuple(dms),
        private_thought=_clean(data.get("private_thought"), 400),
        mood=Mood.parse(data.get("mood")),
    )


def _parse_pledge(raw: dict[str, Any], to: str, view: TableView) -> Pledge | None:
    kind = str(raw.get("pledge") or "").strip().lower()
    if kind not in {"give", "spare", "attack"}:
        return None
    target: str | None = None
    if kind == "attack":
        try:
            target = _resolve_name(raw.get("target"), view)
        except ValueError:
            return None
        if target is None or target in (view.me, to) or target not in view.state.alive_ids:
            return None
    return Pledge(by=view.me, to=to, kind=kind, target=target)


def parse_move(data: dict[str, Any], view: TableView) -> MoveDecision:
    move = Move(
        player=view.me,
        take_from=_resolve_name(data.get("take_from"), view),
        give_to=_resolve_name(data.get("give_to"), view),
    )
    return MoveDecision(
        move=move,
        reasoning=_clean(data.get("reasoning"), 400),
        private_thought=_clean(data.get("private_thought"), 400),
        mood=Mood.parse(data.get("mood")),
    )
