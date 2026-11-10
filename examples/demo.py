"""Show JSON Schema constraint behavior in a compact terminal report."""

import json
import sys

from tcd import JSONSchemaConstraint


USE_COLOR = sys.stdout.isatty()
RESET = "\033[0m"
CYAN = "\033[36m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"


class DemoTokenizer:
    """Expose one complete JSON input as a tokenizer token."""

    def __init__(self, text: str):
        self.text = text

    def get_vocab(self):
        return {self.text: 0}

    def decode(self, token_ids, **kwargs):
        return self.text


def styled(text: str, color: str) -> str:
    if not USE_COLOR:
        return text
    return f"{color}{text}{RESET}"


def run_demo(title: str, schema: dict, input_text: str) -> None:
    print(styled(f"\n{title}", CYAN))
    print(styled("-" * 64, DIM))
    compact_schema = json.dumps(schema, separators=(",", ":"))
    print(styled("schema ", YELLOW) + compact_schema)
    print(styled("input  ", YELLOW) + input_text)

    constraint = JSONSchemaConstraint(schema)
    constraint.bind(DemoTokenizer(input_text))

    try:
        if not constraint.valid_token_ids():
            raise ValueError("input cannot continue the schema")
        constraint.consume_token(0)
        if not constraint.is_complete():
            raise ValueError("input is incomplete")
    except ValueError as error:
        print(styled(f"result   REJECTED  ({error})", RED))
    else:
        print(styled("result   ACCEPTED", GREEN))


CASES = [
    (
        "primitive / string",
        {"type": "string"},
        '"Ada"',
    ),
    (
        "primitive / integer",
        {"type": "integer", "minimum": 0},
        "21",
    ),
    (
        "primitive / boolean",
        {"type": "boolean"},
        "true",
    ),
    (
        "primitive / null",
        {"type": "null"},
        "null",
    ),
    (
        "object / required and optional properties",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        '{"name": "Ada"}',
    ),
    (
        "object / wrong type",
        {
            "type": "object",
            "properties": {"age": {"type": "integer"}},
            "required": ["age"],
            "additionalProperties": False,
        },
        '{"age": "twenty"}',
    ),
    (
        "object / missing required field",
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        "{}",
    ),
    (
        "object / unexpected property",
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        },
        '{"role": "admin"}',
    ),
    (
        "array / nested objects",
        {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
        },
        '[{"id": 1}, {"id": 2}]',
    ),
    (
        "array / invalid item type",
        {"type": "array", "items": {"type": "integer"}},
        "[1, true, 3]",
    ),
]


print(styled("TCD - JSON Schema Constraint Demo", CYAN))
print(styled("Incremental validation through the public JSONSchemaConstraint API", DIM))
for case in CASES:
    run_demo(*case)
print()
