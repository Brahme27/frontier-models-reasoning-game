import pytest

from app.llm.json_utils import extract_json, split_reasoning


class TestSplitReasoning:
    def test_think_tags(self) -> None:
        reasoning, rest = split_reasoning('<think>I should betray Blake</think>\n{"a": 1}')
        assert reasoning == "I should betray Blake"
        assert rest == '{"a": 1}'

    def test_magistral_think_tags(self) -> None:
        reasoning, rest = split_reasoning('[THINK]hmm[/THINK]{"a": 1}')
        assert reasoning == "hmm"
        assert rest == '{"a": 1}'

    def test_no_tags(self) -> None:
        assert split_reasoning('{"a": 1}') == (None, '{"a": 1}')

    def test_unclosed_think_tag_is_all_reasoning(self) -> None:
        reasoning, rest = split_reasoning("<think>still thinking...")
        assert reasoning == "still thinking..."
        assert rest == ""


class TestExtractJson:
    def test_plain_json(self) -> None:
        assert extract_json('{"take_from": "Blake"}') == {"take_from": "Blake"}

    def test_fenced_json(self) -> None:
        text = 'Sure!\n```json\n{"x": [1, 2]}\n```\nGood luck'
        assert extract_json(text) == {"x": [1, 2]}

    def test_json_embedded_in_prose(self) -> None:
        assert extract_json('My move is {"give_to": "Drew", "note": "a {brace}"} ok') == {
            "give_to": "Drew",
            "note": "a {brace}",
        }

    def test_trailing_commas_are_tolerated(self) -> None:
        assert extract_json('{"a": 1, "b": [1, 2,],}') == {"a": 1, "b": [1, 2]}

    def test_picks_last_object_when_model_drafts_first(self) -> None:
        text = 'Draft: {"a": 1}\nFinal: {"a": 2}'
        assert extract_json(text) == {"a": 2}

    def test_raises_when_no_json(self) -> None:
        with pytest.raises(ValueError):
            extract_json("I refuse to play")

    def test_raises_when_top_level_not_object(self) -> None:
        with pytest.raises(ValueError):
            extract_json("[1, 2, 3]")
