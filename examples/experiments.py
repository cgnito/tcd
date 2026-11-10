"""Demonstrate practical regex and JSON Schema constrained generation."""

import json
from contextlib import redirect_stdout
from io import StringIO

from tcd import Decoder, JSONSchemaConstraint, RegexConstraint


def print_section(title: str) -> None:
    """Print a readable heading for one group of demonstrations."""
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def run_json_example(decoder: Decoder, title: str, prompt: str, schema: dict) -> None:
    """Generate and display one schema-constrained JSON response."""
    print(f"\n--- {title} ---")
    print("schema:")
    print(json.dumps(schema, indent=2))

    try:
        with redirect_stdout(StringIO()):
            response = decoder.generate(
                prompt=prompt,
                constraint=JSONSchemaConstraint(schema),
                max_tokens=40,
                temperature=0.8,
            )
        print("generated JSON:")
        print(json.dumps(json.loads(response), indent=2))
    except (ValueError, json.JSONDecodeError) as error:
        print(f"generation failed: {error}")


def run_regex_example(decoder: Decoder, title: str, prompt: str, pattern: str) -> None:
    """Generate and display one regex-constrained response."""
    print(f"\n--- {title} ---")
    print(f"pattern: {pattern}")
    try:
        with redirect_stdout(StringIO()):
            response = decoder.generate(
                prompt=prompt,
                constraint=RegexConstraint(pattern),
                max_tokens=32,
                temperature=0.8,
            )
        print(f"generated text: {response!r}")
    except ValueError as error:
        print(f"generation failed: {error}")


def main() -> None:
    # One decoder can be reused for all examples. The model is loaded only once.
    decoder = Decoder()

    print("TCD constrained generation experiments")
    print("These examples use the public Decoder and constraint APIs.")

    print_section("JSON Schema constraints")
    run_json_example(
        decoder,
        "user profile",
        "Generate a concise user profile.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0},
                "is_student": {"type": "boolean"},
            },
            "required": ["name", "age", "is_student"],
            "additionalProperties": False,
        },
    )
    run_json_example(
        decoder,
        "API response",
        "Return a successful API response with a short message and result.",
        {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "message": {"type": "string"},
                "result": {
                    "type": "object",
                    "properties": {"id": {"type": "integer", "minimum": 1}},
                    "required": ["id"],
                    "additionalProperties": False,
                },
            },
            "required": ["ok", "message", "result"],
            "additionalProperties": False,
        },
    )

    print_section("Regex constraints")
    # The current regex engine supports literals and alternation. These
    # examples use explicit alternatives instead of character classes or '+'.
    run_regex_example(
        decoder,
        "approved email addresses",
        "Return one approved contact email address.",
        "alice@example.com|bob@example.com",
    )
    run_regex_example(
        decoder,
        "support phone numbers",
        "Return one support phone number.",
        "555-0100|555-0101",
    )
    run_regex_example(
        decoder,
        "account identifiers",
        "Return one valid account identifier.",
        "user_1|user_2|admin",
    )


if __name__ == "__main__":
    main()
