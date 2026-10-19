import pytest

from app.game.rules import (
    IllegalMoveError,
    legal_moves,
    new_game,
    resolve_round,
    sanitize_move,
    validate_move,
)
from app.game.state import GameConfig, GameState, Move

IDS = ["alex", "blake", "charlie", "drew"]


def make_game(coins: dict[str, int] | None = None, **cfg: int) -> GameState:
    state = new_game(
        GameConfig(**cfg),
        [(pid, pid.title(), f"model-{pid}") for pid in IDS],
    )
    if coins:
        players = tuple(
            p.model_copy(update={"coins": coins.get(p.id, p.coins)}) for p in state.players
        )
        state = state.model_copy(update={"players": players})
    return state


def moves(*triples: tuple[str, str | None, str | None]) -> list[Move]:
    return [Move(player=p, take_from=t, give_to=g) for p, t, g in triples]


class TestNewGame:
    def test_everyone_starts_with_configured_coins(self) -> None:
        state = make_game(starting_coins=12)
        assert state.coins == {pid: 12 for pid in IDS}
        assert state.round == 0
        assert not state.finished

    def test_requires_unique_players(self) -> None:
        with pytest.raises(ValueError):
            new_game(GameConfig(), [("a", "A", "m"), ("a", "B", "m")])

    def test_requires_at_least_two_players(self) -> None:
        with pytest.raises(ValueError):
            new_game(GameConfig(), [("a", "A", "m")])


class TestValidation:
    def test_cannot_target_self(self) -> None:
        state = make_game()
        with pytest.raises(IllegalMoveError, match="yourself"):
            validate_move(state, Move(player="alex", take_from="alex", give_to="blake"))

    def test_cannot_target_unknown_player(self) -> None:
        state = make_game()
        with pytest.raises(IllegalMoveError, match="not an active player"):
            validate_move(state, Move(player="alex", take_from="zed", give_to="blake"))

    def test_take_and_give_must_differ_with_three_or_more_alive(self) -> None:
        state = make_game()
        with pytest.raises(IllegalMoveError, match="different"):
            validate_move(state, Move(player="alex", take_from="blake", give_to="blake"))

    def test_take_and_give_may_match_when_only_two_alive(self) -> None:
        state = make_game({"charlie": 0, "drew": 0})
        state = state.model_copy(
            update={
                "players": tuple(p.model_copy(update={"alive": p.coins > 0}) for p in state.players)
            }
        )
        validate_move(state, Move(player="alex", take_from="blake", give_to="blake"))

    def test_eliminated_player_cannot_move(self) -> None:
        state = make_game()
        players = tuple(
            p.model_copy(update={"alive": False}) if p.id == "drew" else p for p in state.players
        )
        state = state.model_copy(update={"players": players})
        with pytest.raises(IllegalMoveError, match="not an active player"):
            validate_move(state, Move(player="drew", take_from="alex", give_to="blake"))

    def test_sanitize_turns_illegal_move_into_pass(self) -> None:
        state = make_game()
        move, error = sanitize_move(state, Move(player="alex", take_from="alex", give_to="alex"))
        assert move.is_pass
        assert error is not None

    def test_sanitize_keeps_legal_move(self) -> None:
        state = make_game()
        original = Move(player="alex", take_from="blake", give_to="charlie")
        move, error = sanitize_move(state, original)
        assert move == original
        assert error is None

    def test_legal_moves_includes_pass_and_all_pairs(self) -> None:
        state = make_game()
        options = legal_moves(state, "alex")
        assert Move(player="alex") in options
        assert Move(player="alex", take_from="blake", give_to="charlie") in options
        assert all(validate_move(state, m) is None for m in options)
        # 3 opponents: takes (3 + none) x gives (3 + none) minus 3 same-target pairs
        assert len(options) == 4 * 4 - 3


class TestResolution:
    def test_simple_take_and_give(self) -> None:
        state = make_game()
        new_state, outcome = resolve_round(
            state,
            moves(
                ("alex", "blake", "charlie"),
                ("blake", None, None),
                ("charlie", None, None),
                ("drew", None, None),
            ),
        )
        assert new_state.coins == {"alex": 12, "blake": 11, "charlie": 13, "drew": 12}
        assert outcome.deltas == {"alex": 0, "blake": -1, "charlie": 1, "drew": 0}
        assert new_state.round == 1

    def test_engine_never_mutates_input_state(self) -> None:
        state = make_game()
        before = state.model_dump()
        resolve_round(state, moves(("alex", "blake", "charlie")))
        assert state.model_dump() == before

    def test_mutual_give_pays_alliance_bonus(self) -> None:
        state = make_game(mutual_give_bonus=1)
        new_state, outcome = resolve_round(
            state, moves(("alex", "charlie", "blake"), ("blake", "drew", "alex"))
        )
        # alex: +1 take, -1 give, +1 received, +1 bonus = +2
        assert new_state.coins["alex"] == 14
        assert new_state.coins["blake"] == 14
        assert outcome.mutual_pairs == (("alex", "blake"),)
        assert any(t.kind == "mutual_bonus" for t in outcome.transfers)

    def test_gang_up_pays_each_taker(self) -> None:
        state = make_game(gang_up_bonus=1)
        new_state, outcome = resolve_round(
            state, moves(("alex", "drew", None), ("blake", "drew", None))
        )
        assert new_state.coins["drew"] == 10
        assert new_state.coins["alex"] == 14  # +1 take, +1 gang bonus
        assert new_state.coins["blake"] == 14
        assert outcome.gang_ups[0].victim == "drew"
        assert set(outcome.gang_ups[0].takers) == {"alex", "blake"}

    def test_bonuses_can_be_disabled(self) -> None:
        state = make_game(mutual_give_bonus=0, gang_up_bonus=0)
        new_state, outcome = resolve_round(
            state,
            moves(("alex", "drew", "blake"), ("blake", "drew", "alex")),
        )
        # each: +1 take, -1 give, +1 received; no bank money enters the game
        assert new_state.coins == {"alex": 13, "blake": 13, "charlie": 12, "drew": 10}
        assert not any(t.kind.endswith("bonus") for t in outcome.transfers)
        assert sum(new_state.coins.values()) == sum(state.coins.values())

    def test_balance_never_goes_negative_and_shortfall_is_seeded(self) -> None:
        state = make_game({"drew": 1}, gang_up_bonus=0)
        new_state, outcome = resolve_round(
            state, moves(("alex", "drew", None), ("blake", "drew", None), ("charlie", "drew", None))
        )
        assert new_state.coins["drew"] == 0
        takers_paid = [t.target for t in outcome.transfers if t.kind == "take"]
        assert len(takers_paid) == 1
        # same seed -> same lucky taker
        _, again = resolve_round(
            state, moves(("alex", "drew", None), ("blake", "drew", None), ("charlie", "drew", None))
        )
        assert [t.target for t in again.transfers if t.kind == "take"] == takers_paid

    def test_gang_bonus_only_for_takers_who_actually_took(self) -> None:
        state = make_game({"drew": 1}, gang_up_bonus=1)
        new_state, _ = resolve_round(state, moves(("alex", "drew", None), ("blake", "drew", None)))
        assert sum(new_state.coins[p] for p in ("alex", "blake")) == 12 + 12 + 1 + 1

    def test_broke_giver_cannot_give(self) -> None:
        state = make_game({"alex": 1}, gang_up_bonus=0)
        new_state, outcome = resolve_round(
            state, moves(("alex", None, "charlie"), ("blake", "alex", None))
        )
        assert new_state.coins["alex"] == 0
        assert new_state.coins["charlie"] == 12
        assert not any(t.kind == "give" for t in outcome.transfers)

    def test_zero_coins_eliminates_player(self) -> None:
        state = make_game({"drew": 1})
        new_state, outcome = resolve_round(state, moves(("alex", "drew", None)))
        assert outcome.eliminated == ("drew",)
        drew = new_state.player("drew")
        assert not drew.alive
        assert drew.eliminated_round == 1

    def test_game_finishes_after_max_rounds(self) -> None:
        state = make_game(max_rounds=2)
        state, _ = resolve_round(state, [])
        assert not state.finished
        state, _ = resolve_round(state, [])
        assert state.finished

    def test_game_finishes_when_one_player_left(self) -> None:
        state = make_game({"blake": 1, "charlie": 1, "drew": 1}, gang_up_bonus=0)
        state, _ = resolve_round(
            state,
            moves(
                ("alex", "blake", None),
                ("blake", "charlie", None),
                ("charlie", "drew", None),
                ("drew", "blake", None),
            ),
        )
        # blake was hit twice but only had 1 coin; check survivors
        assert state.finished == (len(state.alive_ids) <= 1)

    def test_cannot_resolve_finished_game(self) -> None:
        state = make_game(max_rounds=1)
        state, _ = resolve_round(state, [])
        with pytest.raises(ValueError, match="finished"):
            resolve_round(state, [])

    def test_missing_moves_default_to_pass(self) -> None:
        state = make_game()
        _, outcome = resolve_round(state, [])
        assert all(m.is_pass for m in outcome.moves)
        assert len(outcome.moves) == 4

    def test_illegal_moves_are_rejected_by_resolver(self) -> None:
        state = make_game()
        with pytest.raises(IllegalMoveError):
            resolve_round(state, moves(("alex", "alex", None)))

    def test_leaders_reports_ties(self) -> None:
        state = make_game({"alex": 15, "blake": 15})
        assert set(state.leaders) == {"alex", "blake"}


class TestSimultaneity:
    """Resolution must not depend on seat order: everyone moves at the same instant."""

    def _game(self, order: list[str], coins: dict[str, int]):
        state = new_game(GameConfig(gang_up_bonus=0), [(p, p, p) for p in order])
        players = tuple(p.model_copy(update={"coins": coins[p.id]}) for p in state.players)
        return state.model_copy(update={"players": players})

    def test_takes_are_order_independent(self) -> None:
        coins = {"a": 1, "b": 12, "c": 12, "d": 12}
        moves_ = [
            Move(player="b", take_from="a"),
            Move(player="c", take_from="a"),
            Move(player="a", take_from="d"),
        ]
        first, _ = resolve_round(self._game(["a", "b", "c", "d"], coins), moves_)
        last, _ = resolve_round(self._game(["b", "c", "d", "a"], coins), moves_)
        assert first.coins["a"] == last.coins["a"] == 1  # paid 1 to its attackers, gained 1
        assert first.player("a").alive and last.player("a").alive

    def test_gifts_received_cannot_fund_your_own_gift(self) -> None:
        coins = {"a": 1, "b": 12, "c": 12, "d": 12}
        moves_ = [
            Move(player="b", take_from="a"),
            Move(player="c", give_to="a"),
            Move(player="a", give_to="d"),
        ]
        for order in (["a", "b", "c", "d"], ["d", "c", "b", "a"]):
            state, outcome = resolve_round(self._game(order, coins), moves_)
            assert not any(t.kind == "give" and t.source == "a" for t in outcome.transfers)
            assert state.coins["a"] == 1  # lost 1 to b, received 1 from c
