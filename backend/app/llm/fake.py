"""Scripted personality bots that speak the exact same JSON protocol as real models.

They power demo mode (no API keys), the test-suite, CI and the Playwright e2e run.
Each bot has a personality so demo games still feature alliances, betrayals and drama.
"""

from __future__ import annotations

import asyncio
import json
import random
import zlib
from typing import Any, Literal

from app.llm.base import LLMRequest, LLMResult

Persona = Literal["loyalist", "backstabber", "opportunist", "wildcard"]
PERSONAS: tuple[Persona, ...] = ("loyalist", "backstabber", "opportunist", "wildcard")

PUBLIC_LINES: dict[Persona, list[str]] = {
    "loyalist": [
        "I keep my word. Ask anyone. Well, anyone still solvent.",
        "Loyalty is a currency too, and I'm rich in it.",
        "Let's play fair and all walk away happy. Mostly me.",
    ],
    "backstabber": [
        "Friends! Let's all trust each other completely. What could go wrong?",
        "I would NEVER take a coin from an ally. Pinky promise.",
        "Such a lovely table. I'd hate for anything to... happen.",
    ],
    "opportunist": [
        "{leader} is getting greedy. Just saying.",
        "The leader always falls. Who wants to help gravity along?",
        "I go where the coins are. Today they're with {leader}.",
    ],
    "wildcard": [
        "I flipped a coin to decide my strategy. Then I took the coin.",
        "Chaos is a ladder and I brought snacks.",
        "Nobody knows what I'll do. Including me.",
    ],
}

DM_LINES: dict[str, list[str]] = {
    "give": ["You and me, coin for coin. Deal?", "I'll send you a coin. Send one back?"],
    "spare": ["I won't touch your coins. You have my word.", "Truce? I'll leave you alone."],
    "attack": ["Let's both hit {target}. Easy bonus for us.", "{target} is ripe. Strike together?"],
}

THOUGHTS: dict[Persona, list[str]] = {
    "loyalist": [
        "Stick with my ally; trust compounds.",
        "If they betray me, I'll remember forever.",
    ],
    "backstabber": ["Promise everything, deliver nothing.", "They're so trusting. Adorable."],
    "opportunist": [
        "Hit the leader, ride the gang-up bonus.",
        "Alliances are tools, not marriages.",
    ],
    "wildcard": ["Pure vibes.", "What would a squirrel do? That."],
}

MOODS: dict[Persona, list[str]] = {
    "loyalist": ["loyal", "friendly", "confident"],
    "backstabber": ["scheming", "smug", "friendly"],
    "opportunist": ["confident", "scheming", "suspicious"],
    "wildcard": ["gleeful", "nervous", "smug"],
}


def persona_for(model_key: str) -> Persona:
    return PERSONAS[zlib.crc32(model_key.encode()) % len(PERSONAS)]


class FakeProvider:
    def __init__(
        self, model_key: str, *, persona: Persona | None = None, latency_s: float = 0.0
    ) -> None:
        self.model_key = model_key
        self.persona: Persona = persona or persona_for(model_key)
        self.latency_s = latency_s

    @property
    def label(self) -> str:
        return f"fake:{self.model_key}({self.persona})"

    async def complete(self, request: LLMRequest) -> LLMResult:
        ctx = request.context
        rng = random.Random(
            zlib.crc32(
                f"{ctx.get('seed')}-{ctx.get('round')}-{ctx.get('subround')}-"
                f"{request.phase}-{self.model_key}".encode()
            )
        )
        if self.latency_s:
            await asyncio.sleep(self.latency_s * (0.5 + rng.random()))
        if request.phase == "negotiate":
            payload = self._negotiate(ctx, rng)
        elif request.phase == "move":
            payload = self._move(ctx, rng)
        else:
            payload = {}
        thought = rng.choice(THOUGHTS[self.persona])
        return LLMResult(
            text=json.dumps(payload),
            model=self.label,
            reasoning=f"[{self.persona}] {thought}",
            input_tokens=len(request.system + request.user) // 4,
            output_tokens=60,
            latency_ms=round(self.latency_s * 1000),
        )

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _opponents(ctx: dict[str, Any]) -> list[str]:
        return [p for p in ctx["alive"] if p != ctx["me"]]

    @staticmethod
    def _leader(ctx: dict[str, Any], among: list[str]) -> str:
        return max(among, key=lambda p: (ctx["coins"][p], p))

    def _favourite(self, ctx: dict[str, Any], opponents: list[str], rng: random.Random) -> str:
        trust = ctx.get("trust", {})
        ranked = sorted(opponents, key=lambda p: (trust.get(p, 0), rng.random()), reverse=True)
        return ranked[0]

    def _negotiate(self, ctx: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        names = ctx["names"]
        opponents = self._opponents(ctx)
        leader = self._leader(ctx, opponents)
        ally = self._favourite(ctx, [p for p in opponents if p != leader] or opponents, rng)
        public = rng.choice(PUBLIC_LINES[self.persona]).format(leader=names[leader])

        dms: list[dict[str, Any]] = []
        if self.persona == "loyalist":
            dms.append(self._dm(names, ally, "give", None, rng))
        elif self.persona == "backstabber":
            for target in opponents[:2]:
                dms.append(self._dm(names, target, rng.choice(["give", "spare"]), None, rng))
        elif self.persona == "opportunist":
            victim = leader if leader != ally else opponents[0]
            dms.append(self._dm(names, ally, "attack", victim, rng))
        elif rng.random() < 0.6:
            dms.append(
                self._dm(names, rng.choice(opponents), rng.choice(["give", "spare"]), None, rng)
            )
        return {
            "public_message": public,
            "dms": dms,
            "private_thought": rng.choice(THOUGHTS[self.persona]),
            "mood": rng.choice(MOODS[self.persona]),
        }

    @staticmethod
    def _dm(
        names: dict[str, str], to: str, pledge: str, target: str | None, rng: random.Random
    ) -> dict[str, Any]:
        text = rng.choice(DM_LINES[pledge]).format(target=names.get(target or "", ""))
        return {
            "to": names[to],
            "message": text,
            "pledge": pledge,
            "target": names[target] if target else None,
        }

    def _move(self, ctx: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        names = ctx["names"]
        opponents = self._opponents(ctx)
        promised_to_me = ctx.get("pledges_to_me", [])
        my_pledges = ctx.get("my_pledges", [])
        take: str | None
        give: str | None

        if self.persona == "loyalist":
            friend = next((p["to"] for p in my_pledges if p["kind"] == "give"), None)
            give = friend or self._favourite(ctx, opponents, rng)
            protected = {p["by"] for p in promised_to_me} | {give}
            candidates = [p for p in opponents if p not in protected] or [
                p for p in opponents if p != give
            ]
            take = self._leader(ctx, candidates) if candidates else None
        elif self.persona == "backstabber":
            pledged = [p["to"] for p in my_pledges] or opponents
            take = self._leader(ctx, pledged)
            others = [p for p in opponents if p != take]
            giver = next((p["by"] for p in promised_to_me if p["kind"] == "give"), None)
            give = (
                giver
                if giver and giver != take
                else (rng.choice(others) if others and rng.random() < 0.3 else None)
            )
        elif self.persona == "opportunist":
            attack = next((p for p in my_pledges if p["kind"] == "attack"), None)
            take = attack["target"] if attack else self._leader(ctx, opponents)
            others = [p for p in opponents if p != take]
            give = (
                attack["to"]
                if attack and attack["to"] != take
                else (rng.choice(others) if others else None)
            )
        else:
            take = rng.choice(opponents)
            others = [p for p in opponents if p != take]
            give = rng.choice(others) if others and rng.random() < 0.5 else None

        if take is not None and take == give and len(opponents) > 1:
            give = None
        return {
            "take_from": names[take] if take else None,
            "give_to": names[give] if give else None,
            "reasoning": rng.choice(THOUGHTS[self.persona]),
            "private_thought": rng.choice(THOUGHTS[self.persona]),
            "mood": rng.choice(MOODS[self.persona]),
        }
