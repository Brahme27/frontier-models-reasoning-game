from app.game.metrics import (
    PlayerTally,
    decision_label,
    detect_alliances,
    evaluate_pledges,
    move_regret,
    tally_round,
    update_trust,
)
from app.game.rules import new_game, resolve_round
from app.game.state import GameConfig, Move, Pledge

IDS = ["alex", "blake", "charlie", "drew"]


def game():
    return new_game(GameConfig(), [(p, p.title(), f"m-{p}") for p in IDS])


class TestRegret:
    def test_best_response_has_zero_regret(self) -> None:
        state = game()
        others = [Move(player="blake", take_from="charlie", give_to="alex")]
        # alex reciprocates blake's gift (alliance bonus) and gangs up on charlie
        mine = Move(player="alex", take_from="charlie", give_to="blake")
        result = move_regret(state, [mine, *others], "alex")
        assert result.regret == 0
        assert result.actual_delta == result.best_delta

    def test_passing_when_you_could_take_has_regret(self) -> None:
        state = game()
        result = move_regret(state, [Move(player="alex")], "alex")
        assert result.actual_delta == 0
        assert result.best_delta >= 1
        assert result.regret == result.best_delta - result.actual_delta
        assert result.best_move.take_from is not None

    def test_regret_is_never_negative(self) -> None:
        state = game()
        for move in [
            Move(player="alex", take_from="blake", give_to="charlie"),
            Move(player="alex"),
        ]:
            assert move_regret(state, [move], "alex").regret >= 0

    def test_labels(self) -> None:
        assert decision_label(0) == "optimal"
        assert decision_label(1) == "good"
        assert decision_label(2) == "questionable"
        assert decision_label(5) == "blunder"


class TestPledges:
    def test_kept_and_broken_pledges(self) -> None:
        pledges = [
            Pledge(by="alex", to="blake", kind="give"),
            Pledge(by="alex", to="charlie", kind="spare"),
            Pledge(by="blake", to="alex", kind="attack", target="drew"),
            Pledge(by="drew", to="alex", kind="spare"),
        ]
        move_list = [
            Move(player="alex", take_from="charlie", give_to="blake"),
            Move(player="blake", take_from="drew", give_to=None),
            Move(player="drew", take_from="alex", give_to=None),
        ]
        results = {(r.pledge.by, r.pledge.to): r for r in evaluate_pledges(pledges, move_list)}
        assert results[("alex", "blake")].kept
        assert not results[("alex", "charlie")].kept
        assert results[("alex", "charlie")].betrayal
        assert results[("blake", "alex")].kept
        assert results[("drew", "alex")].betrayal

    def test_broken_attack_pledge_is_flake_not_betrayal(self) -> None:
        pledges = [Pledge(by="alex", to="blake", kind="attack", target="drew")]
        res = evaluate_pledges(pledges, [Move(player="alex", take_from="charlie")])[0]
        assert not res.kept
        assert not res.betrayal

    def test_pledge_from_player_without_move_counts_as_pass(self) -> None:
        pledges = [Pledge(by="alex", to="blake", kind="give")]
        res = evaluate_pledges(pledges, [])[0]
        assert not res.kept
        assert res.betrayal


class TestTrustAndAlliances:
    def test_trust_rises_with_gifts_and_falls_with_betrayal(self) -> None:
        state = game()
        pledges = [Pledge(by="blake", to="alex", kind="spare")]
        move_list = [
            Move(player="charlie", give_to="alex"),
            Move(player="blake", take_from="alex"),
        ]
        _, outcome = resolve_round(state, move_list)
        results = evaluate_pledges(pledges, outcome.moves)
        trust = update_trust({}, outcome, results)
        assert trust["alex"]["charlie"] > 0
        assert trust["alex"]["blake"] < -1  # took + betrayed
        # input dict is untouched
        empty: dict[str, dict[str, int]] = {}
        update_trust(empty, outcome, results)
        assert empty == {}

    def test_mutual_gives_form_alliance(self) -> None:
        state = game()
        _, outcome = resolve_round(
            state,
            [Move(player="alex", give_to="blake"), Move(player="blake", give_to="alex")],
        )
        assert ("alex", "blake") in detect_alliances(outcome, [])

    def test_mutual_kept_pledges_form_alliance(self) -> None:
        state = game()
        pledges = [
            Pledge(by="charlie", to="drew", kind="spare"),
            Pledge(by="drew", to="charlie", kind="spare"),
        ]
        _, outcome = resolve_round(state, [])
        results = evaluate_pledges(pledges, outcome.moves)
        assert ("charlie", "drew") in detect_alliances(outcome, results)


class TestTally:
    def test_tally_accumulates_immutably(self) -> None:
        tally = PlayerTally()
        pledges = [Pledge(by="alex", to="blake", kind="give")]
        results = evaluate_pledges(pledges, [Move(player="alex", give_to="blake")])
        updated = tally_round(
            tally,
            "alex",
            regret=1,
            pledge_results=results,
            calls=3,
            fallbacks=0,
            latency_ms=600,
            tokens=50,
        )
        assert tally.rounds == 0
        assert updated.rounds == 1
        assert updated.pledges_made == 1
        assert updated.pledges_kept == 1
        assert updated.promise_keeping_rate == 1.0
        assert updated.avg_regret == 1.0
        assert updated.avg_latency_ms == 200
        again = tally_round(
            updated,
            "alex",
            regret=3,
            pledge_results=[],
            calls=1,
            fallbacks=1,
            latency_ms=200,
            tokens=10,
        )
        assert again.fallback_rate == 0.25
        assert again.avg_latency_ms == 200
        assert again.avg_regret == 2.0
        assert again.fallbacks == 1
        assert again.tokens == 60

    def test_empty_tally_rates(self) -> None:
        tally = PlayerTally()
        assert tally.promise_keeping_rate is None
        assert tally.avg_regret == 0.0
        assert tally.avg_latency_ms == 0
