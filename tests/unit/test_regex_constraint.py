import pytest

from tcd import RegexConstraint


class FakeTokenizer:
    def __init__(self):
        self.token_texts = {0: "y", 1: "n", 2: "yes", 3: "no"}

    def get_vocab(self):
        return {text: token_id for token_id, text in self.token_texts.items()}

    def decode(self, token_ids, **kwargs):
        return self.token_texts[token_ids[0]]


def test_regex_constraint_binds_a_tokenizer_and_filters_tokens():
    constraint = RegexConstraint("yes|no")

    constraint.bind(FakeTokenizer())

    assert constraint.valid_token_ids() == [0, 1, 2, 3]


def test_regex_constraint_requires_binding_before_token_lookup():
    constraint = RegexConstraint("yes|no")

    with pytest.raises(RuntimeError, match="bound to a tokenizer"):
        constraint.valid_token_ids()


def test_regex_constraint_commits_tokens_and_reports_completion():
    constraint = RegexConstraint("yes|no")
    constraint.bind(FakeTokenizer())

    constraint.consume_token(2)

    assert constraint.is_complete()