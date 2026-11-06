import pytest

from tcd.schema import ArraySchema, ObjectSchema, PrimitiveSchema, SchemaError, compile_schema


@pytest.mark.parametrize("value_type", ["string", "integer", "boolean", "null"])
def test_compile_schema_builds_primitive_nodes(value_type):
    node = compile_schema({"type": value_type})

    assert node == PrimitiveSchema(value_type)


def test_compile_schema_builds_object_nodes():
    node = compile_schema(
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

    assert node == ObjectSchema(
        properties={
            "name": PrimitiveSchema("string"),
            "age": PrimitiveSchema("integer"),
        },
        required=frozenset({"name"}),
        additional_properties=False,
    )


def test_object_schema_preserves_nested_schema_nodes():
    node = compile_schema(
        {
            "type": "object",
            "properties": {
                "profile": {
                    "type": "object",
                    "properties": {"active": {"type": "boolean"}},
                }
            },
        }
    )

    assert isinstance(node.properties["profile"], ObjectSchema)
    assert node.properties["profile"].properties["active"] == PrimitiveSchema("boolean")


def test_object_schema_rejects_unknown_properties_when_disabled():
    node = compile_schema(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        }
    )

    assert node.allows_property("name")
    assert not node.allows_property("unknown")


def test_compile_schema_preserves_primitive_enum_values():
    node = compile_schema(
        {"type": "string", "enum": ["red", "blue"]}
    )

    assert node == PrimitiveSchema("string", frozenset({"red", "blue"}))


def test_compile_schema_preserves_number_and_string_bounds():
    number_node = compile_schema(
        {"type": "integer", "minimum": 1, "maximum": 10}
    )
    string_node = compile_schema(
        {"type": "string", "minLength": 2, "maxLength": 5}
    )

    assert number_node == PrimitiveSchema("integer", None, 1, 10, None, None)
    assert string_node == PrimitiveSchema("string", None, None, None, 2, 5)


def test_compile_schema_builds_array_item_schema():
    node = compile_schema(
        {"type": "array", "items": {"type": "integer"}}
    )

    assert node == ArraySchema(items=PrimitiveSchema("integer"))


@pytest.mark.parametrize(
    "schema",
    [
        {},
        {"type": "array"},
        {"type": "string", "minimum": 1},
        {"type": "object", "properties": []},
        {"type": "object", "required": "name"},
        {"type": "object", "required": ["missing"]},
        {"type": "object", "additionalProperties": "false"},
        {"type": "string", "enum": []},
        {"type": "string", "enum": "red"},
        {"type": "string", "enum": ["red", 1]},
        {"type": "integer", "enum": [True]},
        {"type": "integer", "minimum": "1"},
        {"type": "integer", "maximum": 1.5},
        {"type": "string", "minLength": -1},
        {"type": "string", "maxLength": "5"},
        {"type": "string", "minLength": 5, "maxLength": 2},
        {"type": "array"},
        {"type": "array", "items": "integer"},
        {"type": "array", "items": {"type": "array"}},
    ],
)
def test_compile_schema_rejects_unsupported_or_invalid_input(schema):
    with pytest.raises(SchemaError):
        compile_schema(schema)