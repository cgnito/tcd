"""Compile the supported JSON Schema subset into internal schema nodes."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping


_PRIMITIVE_TYPES = {"string", "integer", "boolean", "null"}


class SchemaError(ValueError):
    """Indicate that a supplied schema is outside the supported subset."""


@dataclass(frozen=True)
class PrimitiveSchema:
    """Represent a supported JSON primitive type."""

    value_type: str
    enum_values: frozenset[object] | None = None


@dataclass(frozen=True)
class ObjectSchema:
    """Represent an object schema and its property policy."""

    properties: dict[str, SchemaNode]
    required: frozenset[str]
    additional_properties: bool = True

    def allows_property(self, name: str) -> bool:
        """Return whether an object property name is allowed.

        Parameters
        ----------
        name
            Property name to check.

        Returns
        -------
        bool
            ``True`` for declared properties or permitted additional
            properties.
        """
        return name in self.properties or self.additional_properties


SchemaNode = PrimitiveSchema | ObjectSchema


def compile_schema(schema: Mapping[str, object]) -> SchemaNode:
    """Compile one supported JSON Schema node.

    Parameters
    ----------
    schema
        JSON Schema object containing a supported ``type`` declaration.

    Returns
    -------
    SchemaNode
        Internal representation of the schema node.

    Raises
    ------
    SchemaError
        If the schema is malformed or uses unsupported features.
    """
    if not isinstance(schema, Mapping):
        raise SchemaError("schema must be an object")
    if "type" not in schema:
        raise SchemaError("schema must define a type")

    value_type = schema["type"]
    if not isinstance(value_type, str):
        raise SchemaError("schema type must be a string")

    if value_type in _PRIMITIVE_TYPES:
        _reject_unknown_keys(schema, {"type", "enum"})
        enum_values = _compile_enum(schema.get("enum"), value_type)
        return PrimitiveSchema(value_type, enum_values)
    if value_type == "object":
        return _compile_object_schema(schema)
    raise SchemaError(f"unsupported schema type: {value_type!r}")


def _compile_object_schema(schema: Mapping[str, object]) -> ObjectSchema:
    _reject_unknown_keys(schema, {"type", "properties", "required", "additionalProperties"})

    raw_properties = schema.get("properties", {})
    if not isinstance(raw_properties, Mapping):
        raise SchemaError("object properties must be a mapping")

    properties: dict[str, SchemaNode] = {}
    for name, child_schema in raw_properties.items():
        if not isinstance(name, str):
            raise SchemaError("object property names must be strings")
        properties[name] = compile_schema(child_schema)

    raw_required = schema.get("required", [])
    if not isinstance(raw_required, list) or not all(
        isinstance(name, str) for name in raw_required
    ):
        raise SchemaError("required must be a list of property names")
    if len(set(raw_required)) != len(raw_required):
        raise SchemaError("required cannot contain duplicate property names")
    missing = set(raw_required) - properties.keys()
    if missing:
        raise SchemaError(f"required properties are not declared: {sorted(missing)}")

    additional_properties = schema.get("additionalProperties", True)
    if not isinstance(additional_properties, bool):
        raise SchemaError("additionalProperties must be a boolean")

    return ObjectSchema(
        properties=properties,
        required=frozenset(raw_required),
        additional_properties=additional_properties,
    )


def _reject_unknown_keys(schema: Mapping[str, object], allowed: set[str]) -> None:
    unknown = set(schema) - allowed
    if unknown:
        raise SchemaError(f"unsupported schema keywords: {sorted(unknown)}")


def _compile_enum(raw_enum: object, value_type: str) -> frozenset[object] | None:
    if raw_enum is None:
        return None
    if not isinstance(raw_enum, list) or not raw_enum:
        raise SchemaError("enum must be a non-empty list")

    for value in raw_enum:
        if value_type == "string" and not isinstance(value, str):
            raise SchemaError("string enum values must be strings")
        if value_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise SchemaError("integer enum values must be integers")
        if value_type == "boolean" and not isinstance(value, bool):
            raise SchemaError("boolean enum values must be booleans")
        if value_type == "null" and value is not None:
            raise SchemaError("null enum values must be null")

    return frozenset(raw_enum)
