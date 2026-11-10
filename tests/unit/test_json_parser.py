import pytest

from tcd.json_parser import JsonParserState, compile_schema


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


@pytest.mark.parametrize(
    "value",
    [
        "{}",
        "[]",
        '{"name": "Ada", "age": 36}',
        "[1, true, null, \"text\"]",
        '{"user": {"active": true}, "items": [1, 2]}',
    ],
)
def test_parser_accepts_structural_json(value):
    state = JsonParserState()

    state.consume(value)

    assert state.is_complete()


def test_parser_accepts_whitespace_between_json_tokens():
    state = JsonParserState()

    state.consume(' { "name" : "Ada" } ')

    assert state.is_complete()


@pytest.mark.parametrize(
    "value",
    [
        '{"name" "Ada"}',
        '{"name": "Ada" "age": 36}',
        '{"name": "Ada",}',
        "[1 2]",
        "[1,]",
        '{"name": "Ada"]',
        "{]",
    ],
)
def test_parser_rejects_malformed_structure(value):
    state = JsonParserState()

    with pytest.raises(ValueError):
        state.consume(value)


@pytest.mark.parametrize("prefix", ["{", '{"name":', "[", '[{"id": 1},'])
def test_parser_keeps_structural_prefixes_incomplete(prefix):
    state = JsonParserState()

    state.consume(prefix)

    assert not state.is_complete()


def test_schema_parser_accepts_declared_property_types():
    schema = compile_schema(
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "active": {"type": "boolean"},
            },
            "required": ["name", "age", "active"],
            "additionalProperties": False,
        }
    )
    state = JsonParserState(schema)

    state.consume('{"name": "Ada", "age": 36, "active": true}')

    assert state.is_complete()


def test_schema_parser_requires_required_properties_before_object_close():
    schema = compile_schema(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
    )
    state = JsonParserState(schema)

    with pytest.raises(ValueError, match="required"):
        state.consume("{}")


@pytest.mark.parametrize(
    "value",
    [
        '{"name": 42}',
        '{"age": "36"}',
        '{"active": null}',
    ],
)
def test_schema_parser_rejects_property_type_mismatches(value):
    schema = compile_schema(
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "active": {"type": "boolean"},
            },
        }
    )
    state = JsonParserState(schema)

    with pytest.raises(ValueError, match="type"):
        state.consume(value)


def test_schema_parser_rejects_unknown_and_duplicate_properties():
    schema = compile_schema(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        }
    )

    with pytest.raises(ValueError, match="unknown"):
        JsonParserState(schema).consume('{"unknown": true}')

    with pytest.raises(ValueError, match="duplicate"):
        JsonParserState(schema).consume('{"name": "Ada", "name": "Grace"}')


def test_schema_parser_allows_optional_and_additional_properties_by_policy():
    schema = compile_schema(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": True,
        }
    )
    state = JsonParserState(schema)

    state.consume('{"other": false}')

    assert state.is_complete()


def test_schema_parser_applies_nested_object_schema():
    schema = compile_schema(
        {
            "type": "object",
            "properties": {
                "profile": {
                    "type": "object",
                    "properties": {"active": {"type": "boolean"}},
                    "required": ["active"],
                    "additionalProperties": False,
                }
            },
            "required": ["profile"],
        }
    )

    state = JsonParserState(schema)
    state.consume('{"profile": {"active": true}}')

    assert state.is_complete()


def test_schema_parser_enforces_string_enum_values():
    schema = compile_schema(
        {
            "type": "object",
            "properties": {
                "color": {"type": "string", "enum": ["red", "blue"]}
            },
        }
    )

    valid_state = JsonParserState(schema)
    valid_state.consume('{"color": "red"}')
    assert valid_state.is_complete()

    with pytest.raises(ValueError, match="enum"):
        JsonParserState(schema).consume('{"color": "green"}')


def test_schema_parser_allows_optional_properties_in_any_order():
    schema = compile_schema(
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
            "additionalProperties": False,
        }
    )

    state = JsonParserState(schema)
    state.consume('{"age": 36, "name": "Ada"}')

    assert state.is_complete()


def test_schema_parser_enforces_array_item_types():
    schema = compile_schema(
        {"type": "array", "items": {"type": "integer"}}
    )

    state = JsonParserState(schema)
    state.consume("[1, 2, 3]")

    assert state.is_complete()

    with pytest.raises(ValueError, match="type"):
        JsonParserState(schema).consume("[1, true]")


def test_schema_parser_accepts_empty_arrays_and_nested_object_items():
    array_schema = compile_schema(
        {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
        }
    )

    empty_state = JsonParserState(array_schema)
    empty_state.consume("[]")
    assert empty_state.is_complete()

    nested_state = JsonParserState(array_schema)
    nested_state.consume('[{"id": 1}, {"id": 2}]')
    assert nested_state.is_complete()


def test_schema_parser_enforces_number_bounds():
    schema = compile_schema(
        {
            "type": "object",
            "properties": {"age": {"type": "integer", "minimum": 18, "maximum": 65}},
        }
    )

    valid_state = JsonParserState(schema)
    valid_state.consume('{"age": 18}')
    assert valid_state.is_complete()

    for value in ("17", "66"):
        with pytest.raises(ValueError, match="bound"):
            JsonParserState(schema).consume(f'{{"age": {value}}}')


def test_schema_parser_enforces_string_length_bounds():
    schema = compile_schema(
        {
            "type": "object",
            "properties": {"code": {"type": "string", "minLength": 2, "maxLength": 4}},
        }
    )

    valid_state = JsonParserState(schema)
    valid_state.consume('{"code": "abcd"}')
    assert valid_state.is_complete()

    for value in ("a", "abcde"):
        with pytest.raises(ValueError, match="length"):
            JsonParserState(schema).consume(f'{{"code": "{value}"}}')