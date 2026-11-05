# Constraint Flow Overview

The model generates token IDs, while the constraint state machines understand
characters and JSON structure. A constraint bridges those two worlds:

```text
model token ID
    -> cached decoded text
    -> constraint state machine
    -> valid or invalid continuation
```

## Public API

Regex constraints use the regex-backed DFA:

```python
from tcd import Decoder, RegexConstraint

decoder = Decoder()

response = decoder.generate(
    prompt="Is Python a programming language?",
    constraint=RegexConstraint("yes|no"),
)
```


JSON constraints use the schema-backed parser:

```python
from tcd import Decoder, JSONSchemaConstraint

schema = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}

response = Decoder().generate(
    prompt="Generate a user profile.",
    constraint=JSONSchemaConstraint(schema),
)
```

The decoder does not need to know whether a constraint uses a DFA or a JSON
parser. Both provide the same operations:

```text
bind(tokenizer)
valid_token_ids()
consume_token(token_id)
is_complete()
```

## TokenIndex

`TokenIndex` is shared by both constraint types. It is not a JSON-only or
regex-only component.

When a constraint is bound to the decoder's tokenizer, `TokenIndex`:

1. Decodes each vocabulary token once.
2. Caches decoded text by token ID.
3. Groups tokens by their first decoded character.

For example:

```text
"{"  -> [(0, "{")]
"\"" -> [(1, "\"name\""), (3, "\"Ada\"")]
":"  -> [(2, ":")]
```

The index does not decide validity. It only returns possible candidates. The
constraint's state machine checks whether each complete token can be consumed.

Most states use the first-character buckets. While inside a JSON string, any
non-control character may be valid, so the JSON constraint may inspect all
cached entries and reject tokens containing invalid text.

## Regex Flow

Suppose the constraint is:

```python
RegexConstraint("yes|no")
```

### 1. Build the DFA

The regex becomes a DFA:

```text
q0 --y--> q1 --e--> q2 --s--> q3 accepting
 |
 n
 v
q4 --o--> q5 accepting
```

At `q0`, the DFA reports the valid next symbols:

```python
{"y", "n"}
```

### 2. Find candidate tokens

`RegexConstraint` asks the shared index for tokens beginning with `y` or `n`:

```text
"y"
"n"
"yes"
"no"
"yea"
```

### 3. Simulate complete token text

A token is not validated only by its first character. Its entire decoded text
must follow DFA transitions.

```text
candidate: "yes"

q0 --y--> q1
q1 --e--> q2
q2 --s--> q3

valid
```

But:

```text
candidate: "yea"

q0 --y--> q1
q1 --e--> q2
q2 --a--> invalid

reject
```

The valid token IDs are returned to the decoder.

### 4. Mask and sample

The decoder keeps valid logits and sets every other logit to negative infinity.
An invalid token therefore has zero probability and cannot be sampled.

### 5. Commit the selected token

If the model selects the token `"yes"`, the constraint uses its cached text and
moves the real DFA:

```text
q0 -> q1 -> q2 -> q3
```

Since `q3` is accepting, generation stops.

## JSON Flow

Suppose the schema requires a single string property:

```python
{
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}
```

### 1. Create parser state

`JSONSchemaConstraint` creates a schema-aware `JsonParserState`:

```text
root parser state
no object has started
empty stack
```

Unlike the regex DFA, the JSON parser uses a stack because objects and arrays
can be nested:

```text
root object
    nested object
        array
```

### 2. Ask for valid symbols

The schema says the root must be an object, so although JSON generally allows
many value starts, the parser only allows:

```text
{
```

### 3. Find and simulate candidates

The JSON constraint asks `TokenIndex` for tokens beginning with `{`, then tests
each complete token using `parser.can_consume(token_text)`.

The token `"{"` is valid. A token beginning with `[` is rejected because the
schema requires an object.

### 4. Commit structure

After selecting `{`, the parser pushes an object frame containing:

```text
schema
seen properties
pending property
pending value schema
current parsing phase
```

The next valid property name must be quoted. With
`additionalProperties=False`, `"unknown"` is rejected and `"name"` is
accepted.

The expected flow is:

```text
{
    -> "name"
    -> :
    -> "Ada"
    -> }
```

When `}` is tested, the parser checks that all required properties were seen.
If `name` was present, the object can complete.

## Candidate Simulation and Commitment

`can_consume(text)` is simulation. It copies the current JSON parser state,
tries every character of the candidate text, and returns `True` or `False`:

```text
real parser state
        |
        | copy
        v
candidate parser state
        |
try candidate token text
        |
True or False
```

The real parser state does not change during candidate lookup. Only the token
selected by the model is committed with `consume_token(token_id)`.

Regex uses the same idea in `_can_consume(text)`, but it copies a local DFA
state instead of a JSON parser stack.

```text
RegexConstraint
    TokenIndex + DFA simulation

JSONSchemaConstraint
    TokenIndex + JSON parser simulation
```

## Complete Decoder Flow

Every generation step follows the same contract:

```text
1. bind the constraint to the tokenizer
2. run the model and get next-token logits
3. ask the constraint for valid token IDs
4. use those IDs to mask invalid logits
5. sample one token ID
6. commit the token through consume_token()
7. stop if is_complete() is true
8. otherwise run the model again
```

The state machines remain different:

```text
regex pattern
    -> NFA
    -> DFA
    -> RegexConstraint

JSON Schema
    -> schema nodes
    -> parser state + stack
    -> JSONSchemaConstraint
```

They share the decoder contract and `TokenIndex`, not one implementation of
state. A DFA is appropriate for the finite state of the supported regexes;
JSON nesting requires parser frames and a stack.

## Important Tokenization Detail

The model predicts token IDs, not text. The tokenizer index decodes the
vocabulary once before generation:

```text
Before generation:
    decode and index vocabulary once.

At each step:
    find candidate buckets.
    simulate complete token text.
    return valid token IDs.

After sampling:
    use cached token text.
    commit it to the DFA or JSON parser.
```

The tokenizer does not repeatedly decode every token before every prediction.
That was the original expensive approach. `TokenIndex` avoids that repeated
work.

The current implementation decodes token IDs independently. Byte-level,
context-sensitive, special-token, and more complex token-boundary behavior are
future tokenizer-integration work.
