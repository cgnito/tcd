import json

from tcd import Decoder, JSONSchemaConstraint


decoder = Decoder()
prompt = "Answer according to the supplied constraint."
constraints = [
    ("regex yes/no", "yes|no"),
    ("regex animals", "cat|dog"),
    (
        "json profile",
        JSONSchemaConstraint(
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer", "minimum": 0},
                    "is_student": {"type": "boolean"},
                },
                "required": ["name", "age", "is_student"],
                "additionalProperties": False,
            }
        ),
    ),
]

print("prompt:", prompt)
print()

for label, constraint in constraints:
    print(f"constraint: {label}")
    try:
        response = decoder.generate(
            prompt=prompt,
            constraint=constraint,
            max_tokens=30,
            temperature=0.8,
        )
        print("response:", repr(response))
        if label == "json profile":
            print("parsed JSON:", json.loads(response))
    except ValueError as error:
        print("constraint failed:", error)
    print()
