import pytest

from tcd.schema import ObjectSchema, PrimitiveSchema, SchemaError, compile_schema


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
    ],
)
def test_compile_schema_rejects_unsupported_or_invalid_input(schema):
    with pytest.raises(SchemaError):
        compile_schema(schema)