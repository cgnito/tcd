"""Benchmark task definitions.

Each Task pairs a natural-language prompt with a JSON Schema and metadata.
The same prompt and schema are used by all three benchmark strategies so that
the only variable between approaches is the generation method itself.

Prompts describe the required fields in plain prose rather than embedding a
raw schema. This reflects realistic prompting practice and gives Approach A
(normal prompting) and Approach B (validation and retry) a representative but
genuinely challenging baseline.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    """One benchmark task.

    Attributes
    ----------
    task_id
        Short identifier used in results files and log output, e.g. ``"TC-1"``.
    description
        Human-readable note on what this task is designed to measure.
    prompt
        The generation prompt sent to the model. All three approaches receive
        the identical prompt so that generation method is the only variable.
    schema
        JSON Schema dict passed to ``JSONSchemaConstraint`` (Approach C) and
        to ``jsonschema.validate`` for output validation (all approaches).
    """

    task_id: str
    description: str
    prompt: str
    schema: dict


TASKS: list[Task] = [
    Task(
        task_id="TC-1",
        description=(
            "Flat object with two string fields. "
            "Establishes the baseline: minimal schema, shortest output, "
            "fewest ways for unconstrained generation to fail."
        ),
        prompt=(
            "Generate a JSON object with exactly two fields: "
            "name, which is a string, and status, which is a string. "
            "Respond with only the JSON object and nothing else."
        ),
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["name", "status"],
            "additionalProperties": False,
        },
    ),
    Task(
        task_id="TC-2",
        description=(
            "Flat object with three fields spanning all three basic primitive "
            "types: string, integer, and boolean. "
            "Tests whether unconstrained generation can maintain type discipline "
            "across a small mixed-type object."
        ),
        prompt=(
            "Generate a JSON object for a user record with exactly three fields: "
            "username, which is a string; "
            "score, which is a non-negative integer; "
            "and active, which is a boolean. "
            "Respond with only the JSON object and nothing else."
        ),
        schema={
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "score": {"type": "integer", "minimum": 0},
                "active": {"type": "boolean"},
            },
            "required": ["username", "score", "active"],
            "additionalProperties": False,
        },
    ),
    Task(
        task_id="TC-3",
        description=(
            "Flat object with four required fields including two bounded integers. "
            "Tests whether unconstrained generation respects numeric constraints "
            "described only in prose, and whether TCD overhead scales with "
            "the number of required fields."
        ),
        prompt=(
            "Generate a JSON object for a book record with exactly four fields: "
            "title, which is a string; "
            "year, which is an integer between 1900 and 2100; "
            "rating, which is an integer between 1 and 10; "
            "and available, which is a boolean. "
            "Respond with only the JSON object and nothing else."
        ),
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "year": {"type": "integer", "minimum": 1900, "maximum": 2100},
                "rating": {"type": "integer", "minimum": 1, "maximum": 10},
                "available": {"type": "boolean"},
            },
            "required": ["title", "year", "rating", "available"],
            "additionalProperties": False,
        },
    ),
    Task(
        task_id="TC-4",
        description=(
            "Nested object: an outer object containing an inner object and a "
            "string field. "
            "Tests TCD parser stack depth and whether unconstrained generation "
            "can correctly close both the inner and outer objects."
        ),
        prompt=(
            "Generate a JSON object with exactly two fields: "
            "user, which is itself an object containing id as a positive integer "
            "and name as a string; "
            "and message, which is a string. "
            "Respond with only the JSON object and nothing else."
        ),
        schema={
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "minimum": 1},
                        "name": {"type": "string"},
                    },
                    "required": ["id", "name"],
                    "additionalProperties": False,
                },
                "message": {"type": "string"},
            },
            "required": ["user", "message"],
            "additionalProperties": False,
        },
    ),
    Task(
        task_id="TC-5",
        description=(
            "Array of objects: each element is an object with an integer and a "
            "string field. "
            "Tests TCD array handling and produces the longest outputs in the "
            "dataset. Unconstrained generation must balance correct array syntax, "
            "correct object structure, and correct closing brackets."
        ),
        prompt=(
            "Generate a JSON array containing two or three elements. "
            "Each element must be an object with exactly two fields: "
            "id, which is a positive integer, and tag, which is a string. "
            "Respond with only the JSON array and nothing else."
        ),
        schema={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "minimum": 1},
                    "tag": {"type": "string"},
                },
                "required": ["id", "tag"],
                "additionalProperties": False,
            },
        },
    ),
]
