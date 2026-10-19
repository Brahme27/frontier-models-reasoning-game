"""The pure, deterministic Outsmart rules engine.

Round resolution (all moves are simultaneous and secret):

1. **Takes**: every taker grabs 1 coin from their victim. A victim can lose at most the coins
   it started the round with; if it runs short, a seeded shuffle decides which takers got paid.
2. **Gives**: every giver hands 1 coin to their chosen player if they still hold one after
   the takes (gifts received this round can't be re-gifted).
3. **Alliance bonus**: two players who gave to *each other* both receive a bonus from the bank.
4. **Gang-up bonus**: when 2+ players take from the same victim, each successful taker
   receives a bonus from the bank (coordinated attacks pay).
5. **Elimination**: anyone at 0 coins is out. The game ends after ``max_rounds`` or when
   at most one player is left standing.

No function here mutates its inputs; new ``GameState`` objects are returned instead.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence

from app.game.state import (
    GameConfig,
    GameState,
    GangUp,
    Move,
    PlayerState,
    RoundOutcome,
    Transfer,
)


class IllegalMoveError(ValueError):
    """Raised when a move breaks the rules."""


def new_game(config: GameConfig, roster: Sequence[tuple[str, str, str]]) -> GameState:
    """Create a fresh game. ``roster`` is a sequence of (player_id, name, model_key)."""
    ids = [pid for pid, _, _ in roster]
    if len(ids) < 2:
        raise ValueError("Outsmart needs at least two players")
    if len(set(ids)) != len(ids):
        raise ValueError("player ids must be unique")
    players = tuple(
        PlayerState(id=pid, name=name, model_key=model_key, coins=config.starting_coins)
        for pid, name, model_key in roster
    )
    return GameState(config=config, players=players)


def validate_move(state: GameState, move: Move) -> None:
    """Raise ``IllegalMoveError`` if ``move`` is not allowed in ``state``."""
    alive = set(state.alive_ids)
    if move.player not in alive:
        raise IllegalMoveError(f"{move.player} is not an active player")
    for label, target in (("take from", move.take_from), ("give to", move.give_to)):
        if target is None:
            continue
        if target == move.player:
            raise IllegalMoveError(f"you cannot {label} yourself")
        if target not in alive:
            raise IllegalMoveError(f"{target} is not an active player")
    if move.take_from is not None and move.take_from == move.give_to and len(alive) > 2:
        raise IllegalMoveError("take_from and give_to must be different players")


def sanitize_move(state: GameState, move: Move) -> tuple[Move, str | None]:
    """Return ``(move, None)`` if legal, otherwise ``(pass_move, reason)``."""
    try:
        validate_move(state, move)
    except IllegalMoveError as exc:
        return Move(player=move.player), str(exc)
    return move, None


def legal_moves(state: GameState, player_id: str) -> list[Move]:
    """Every legal move for ``player_id`` (including passing)."""
    targets: list[str | None] = [None, *(p for p in state.alive_ids if p != player_id)]
    options: list[Move] = []
    for take in targets:
        for give in targets:
            candidate = Move(player=player_id, take_from=take, give_to=give)
            try:
                validate_move(state, candidate)
            except IllegalMoveError:
                continue
            options.append(candidate)
    return options


def _round_rng(config: GameConfig, round_no: int) -> random.Random:
    return random.Random(config.seed * 10_007 + round_no)


def _complete_moves(state: GameState, moves: Iterable[Move]) -> tuple[Move, ...]:
    by_player: dict[str, Move] = {}
    for move in moves:
        validate_move(state, move)
        by_player[move.player] = move
    return tuple(by_player.get(pid, Move(player=pid)) for pid in state.alive_ids)


def resolve_round(state: GameState, moves: Iterable[Move]) -> tuple[GameState, RoundOutcome]:
    """Apply one round of simultaneous moves and return the new state plus what happened."""
    if state.finished:
        raise ValueError("game is already finished")

    round_no = state.round + 1
    cfg = state.config
    rng = _round_rng(cfg, round_no)
    full_moves = _complete_moves(state, moves)
    balances = dict(state.coins)
    transfers: list[Transfer] = []

    # 1. takes
    takers_by_victim: dict[str, list[str]] = {}
    for move in full_moves:
        if move.take_from is not None:
            takers_by_victim.setdefault(move.take_from, []).append(move.player)

    # A victim can only lose the coins it held when the round began, so coins it grabs
    # itself this round never fund its own losses: the outcome is independent of seat order.
    successful_takers: dict[str, set[str]] = {}
    for victim in state.alive_ids:
        takers = list(takers_by_victim.get(victim, []))
        rng.shuffle(takers)
        for taker in takers[: state.coins[victim]]:
            balances[victim] -= 1
            balances[taker] += 1
            transfers.append(Transfer(source=victim, target=taker, amount=1, kind="take"))
            successful_takers.setdefault(victim, set()).add(taker)

    # 2. gives, judged on post-take balances so a gift received cannot fund your own gift
    after_takes = dict(balances)
    executed_gives: set[tuple[str, str]] = set()
    for move in full_moves:
        if move.give_to is None or after_takes[move.player] <= 0:
            continue
        balances[move.player] -= 1
        balances[move.give_to] += 1
        transfers.append(Transfer(source=move.player, target=move.give_to, amount=1, kind="give"))
        executed_gives.add((move.player, move.give_to))

    # 3. alliance bonus for mutual gives
    order = {pid: i for i, pid in enumerate(state.alive_ids)}
    mutual_pairs: list[tuple[str, str]] = []
    for giver, receiver in sorted(executed_gives):
        if order[giver] < order[receiver] and (receiver, giver) in executed_gives:
            mutual_pairs.append((giver, receiver))
    mutual_pairs.sort(key=lambda pair: (order[pair[0]], order[pair[1]]))
    if cfg.mutual_give_bonus > 0:
        for pair in mutual_pairs:
            for pid in pair:
                balances[pid] += cfg.mutual_give_bonus
                transfers.append(
                    Transfer(
                        source=None, target=pid, amount=cfg.mutual_give_bonus, kind="mutual_bonus"
                    )
                )

    # 4. gang-up bonus
    gang_ups = tuple(
        GangUp(victim=victim, takers=tuple(takers))
        for victim, takers in takers_by_victim.items()
        if len(takers) >= 2
    )
    if cfg.gang_up_bonus > 0:
        for gang in gang_ups:
            for taker in gang.takers:
                if taker in successful_takers.get(gang.victim, set()):
                    balances[taker] += cfg.gang_up_bonus
                    transfers.append(
                        Transfer(
                            source=None, target=taker, amount=cfg.gang_up_bonus, kind="gang_bonus"
                        )
                    )

    # 5. elimination
    eliminated = tuple(pid for pid in state.alive_ids if balances[pid] <= 0)
    players = tuple(_update_player(p, balances[p.id], round_no, eliminated) for p in state.players)
    alive_count = sum(1 for p in players if p.alive)
    new_state = state.model_copy(
        update={
            "players": players,
            "round": round_no,
            "finished": round_no >= cfg.max_rounds or alive_count <= 1,
        }
    )
    outcome = RoundOutcome(
        round=round_no,
        moves=full_moves,
        transfers=tuple(transfers),
        deltas={pid: balances[pid] - state.coins[pid] for pid in state.coins},
        mutual_pairs=tuple(mutual_pairs),
        gang_ups=gang_ups,
        eliminated=eliminated,
    )
    return new_state, outcome


def _update_player(
    player: PlayerState, coins: int, round_no: int, eliminated: tuple[str, ...]
) -> PlayerState:
    if player.id in eliminated:
        return player.model_copy(update={"coins": 0, "alive": False, "eliminated_round": round_no})
    return player.model_copy(update={"coins": coins})
