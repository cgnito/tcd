from tcd import Decoder


decoder = Decoder()
prompt = "Answer with one short word. Is Python a programming language?"
constraints = [
    "yes|no",
    "cat|dog",
    "red|blue|green",
    "a(b|c)",
]

print("prompt:", prompt)
print()

for pattern in constraints:
    print(f"constraint: {pattern!r}")
    try:
        response = decoder.generate(
            prompt=prompt,
            constraint=pattern,
            max_tokens=10,
            temperature=0.8,
        )
        print("response:", repr(response))
    except ValueError as error:
        print("constraint failed:", error)
    print()
