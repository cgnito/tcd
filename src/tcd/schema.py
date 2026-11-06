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
    minimum: int | None = None
    maximum: int | None = None
    min_length: int | None = None
    max_length: int | None = None


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


@dataclass(frozen=True)
class ArraySchema:
    """Represent an array whose elements share one schema."""

    items: SchemaNode


SchemaNode = PrimitiveSchema | ObjectSchema | ArraySchema


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
        allowed_keys = {"type", "enum"}
        if value_type == "integer":
            allowed_keys |= {"minimum", "maximum"}
        if value_type == "string":
            allowed_keys |= {"minLength", "maxLength"}
        _reject_unknown_keys(schema, allowed_keys)
        enum_values = _compile_enum(schema.get("enum"), value_type)
        minimum = _compile_bound(schema.get("minimum"), "minimum", value_type)
        maximum = _compile_bound(schema.get("maximum"), "maximum", value_type)
        min_length = _compile_length(schema.get("minLength"), "minLength", value_type)
        max_length = _compile_length(schema.get("maxLength"), "maxLength", value_type)
        if (
            min_length is not None
            and max_length is not None
            and min_length > max_length
        ):
            raise SchemaError("minLength cannot exceed maxLength")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise SchemaError("minimum cannot exceed maximum")
        return PrimitiveSchema(
            value_type,
            enum_values,
            minimum,
            maximum,
            min_length,
            max_length,
        )
    if value_type == "object":
        return _compile_object_schema(schema)
    if value_type == "array":
        return _compile_array_schema(schema)
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


def _compile_array_schema(schema: Mapping[str, object]) -> ArraySchema:
    _reject_unknown_keys(schema, {"type", "items"})
    if "items" not in schema:
        raise SchemaError("array schema must define items")
    items = schema["items"]
    if not isinstance(items, Mapping):
        raise SchemaError("array items must be a schema object")
    return ArraySchema(items=compile_schema(items))


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


def _compile_bound(raw_bound: object, name: str, value_type: str) -> int | None:
    if raw_bound is None:
        return None
    if value_type != "integer":
        raise SchemaError(f"{name} is only supported for integer schemas")
    if not isinstance(raw_bound, int) or isinstance(raw_bound, bool):
        raise SchemaError(f"{name} must be an integer")
    return raw_bound


def _compile_length(raw_length: object, name: str, value_type: str) -> int | None:
    if raw_length is None:
        return None
    if value_type != "string":
        raise SchemaError(f"{name} is only supported for string schemas")
    if not isinstance(raw_length, int) or isinstance(raw_length, bool) or raw_length < 0:
        raise SchemaError(f"{name} must be a non-negative integer")
    return raw_length
