import pytest

from tcd import JSONSchemaConstraint


class FakeTokenizer:
    def __init__(self, token_texts):
        self.token_texts = token_texts
        self.decode_calls = 0

    def get_vocab(self):
        return {text: token_id for token_id, text in self.token_texts.items()}

    def decode(self, token_ids, **kwargs):
        self.decode_calls += 1
        return self.token_texts[token_ids[0]]


def profile_schema():
    return {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }


def test_json_constraint_filters_tokens_using_parser_state():
    tokenizer = FakeTokenizer(
        {
            0: "{",
            1: '"name"',
            2: '"unknown"',
            3: ":",
            4: '"Ada"',
            5: "}",
        }
    )
    constraint = JSONSchemaConstraint(profile_schema())
    constraint.bind(tokenizer)

    assert constraint.valid_token_ids() == [0]

    constraint.consume_token(0)
    assert constraint.valid_token_ids() == [1]

    constraint.consume_token(1)
    assert constraint.valid_token_ids() == [3]

    constraint.consume_token(3)
    assert constraint.valid_token_ids() == [1, 2, 4]

    constraint.consume_token(4)
    assert constraint.valid_token_ids() == [5]

    constraint.consume_token(5)
    assert constraint.is_complete()


def test_json_constraint_candidate_lookup_does_not_mutate_parser_state():
    tokenizer = FakeTokenizer({0: "{", 1: '"name"', 2: ":"})
    constraint = JSONSchemaConstraint(profile_schema())
    constraint.bind(tokenizer)

    constraint.valid_token_ids()

    assert not constraint.is_complete()
    assert constraint.valid_token_ids() == [0]


def test_json_constraint_reuses_decoded_token_text():
    tokenizer = FakeTokenizer({0: "{", 1: '"name"', 2: ":"})
    constraint = JSONSchemaConstraint(profile_schema())
    constraint.bind(tokenizer)

    assert tokenizer.decode_calls == 3
    constraint.valid_token_ids()
    constraint.consume_token(0)
    constraint.valid_token_ids()

    assert tokenizer.decode_calls == 3


def test_json_constraint_reports_when_no_token_can_continue():
    constraint = JSONSchemaConstraint(profile_schema())
    constraint.bind(FakeTokenizer({0: "["}))

    assert constraint.valid_token_ids() == []


def test_json_constraint_requires_binding_before_lookup():
    constraint = JSONSchemaConstraint(profile_schema())

    with pytest.raises(RuntimeError, match="bound to a tokenizer"):
        constraint.valid_token_ids()