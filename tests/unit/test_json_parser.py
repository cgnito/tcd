import pytest

from tcd.json_parser import JsonParserState


@pytest.mark.parametrize(
    "value",
    [
        '"hello"',
        '"hello\\\"world"',
        "0",
        "42",
        "-7",
        "true",
        "false",
        "null",
    ],
)
def test_parser_accepts_complete_primitive_values(value):
    state = JsonParserState()

    state.consume(value)

    assert state.is_complete()


@pytest.mark.parametrize("prefix", ['"hello', "tru", "-", "fals", "n"])
def test_parser_keeps_valid_incomplete_prefixes_open(prefix):
    state = JsonParserState()

    state.consume(prefix)

    assert not state.is_complete()


def test_parser_reports_literal_continuations():
    state = JsonParserState()

    state.consume("tru")

    assert state.valid_symbols() == {"e"}


def test_parser_reports_number_continuations():
    state = JsonParserState()

    state.consume("-")

    assert state.valid_symbols() == set("0123456789")


def test_parser_allows_non_control_characters_inside_strings():
    state = JsonParserState()

    state.consume('"hello')

    assert state.valid_symbols() is None
    assert state.can_consume(' world"')


@pytest.mark.parametrize(
    "value",
    [
        "truX",
        "01",
        '"hello\nworld"',
        '"bad\\x"',
        '"hello"tail',
    ],
)
def test_parser_rejects_invalid_primitive_input(value):
    state = JsonParserState()

    with pytest.raises(ValueError):
        state.consume(value)


def test_candidate_validation_does_not_mutate_parser_state():
    state = JsonParserState()
    state.consume("tru")

    assert not state.can_consume("X")
    assert state.can_consume("e")

    state.consume("e")

    assert state.is_complete()