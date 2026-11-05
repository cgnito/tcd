# Constraint Flow Overview

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

At `q0`, the DFA reports:

```python
{"y", "n"}
```

### 2. Find candidate token buckets

The regex constraint asks:

```python
token_index.entries({"y", "n"})
```

This returns tokens whose first character is `y` or `n`.

For example:

```text
"y"
"n"
"yes"
"no"
"yea"
```

### 3. Check every complete token

Each candidate is simulated character by character:

```text
candidate: "yes"

q0 --y--> q1
q1 --e--> q2
q2 --s--> q3

valid
```

For:

```text
candidate: "yea"
```

the final transition fails:

```text
q0 --y--> q1
q1 --e--> q2
q2 --a--> invalid

reject
```

The valid token IDs are returned to the decoder.

### 4. Decoder masks logits

The decoder creates a mask:

```text
valid token IDs -> unchanged logits
all other IDs    -> -infinity
```

Then it samples from the remaining tokens.

### 5. Commit the selected token

If the model selects the token `"yes"`:

```python
constraint.consume_token(token_id)
```

The regex constraint uses the cached text `"yes"` and moves the real DFA:

```text
q0 -> q1 -> q2 -> q3
```

Since `q3` is accepting, generation stops.

## JSON Flow

Suppose the schema is:

```python
{
    "type": "object",
    "properties": {
        "name": {"type": "string"},
    },
    "required": ["name"],
    "additionalProperties": False,
}
```

### 1. Create the JSON parser state

`JSONSchemaConstraint` creates:

```text
JsonParserState(schema)
```

Initially:

```text
parser is at the root
no object has started
```

### 2. Ask the parser for valid symbols

At the root, valid JSON starts include:

```text
{
[
"
-
digits
true
false
null
```

But because the root schema is an object, the schema-aware parser only allows:

```text
{
```

### 3. Use TokenIndex

The JSON constraint asks `TokenIndex` for tokens beginning with `{`.

Possible candidates:

```text
"{"
"{\"name\""
"["
```

Then each candidate is checked with:

```python
parser.can_consume(token_text)
```

The token `"{"` is valid. The token `"["` is rejected because the schema requires an object.

### 4. Decoder masks and samples

The decoder receives the valid token ID for `"{"`, masks everything else, and samples it.

### 5. Commit the selected token

The JSON constraint calls:

```python
parser.consume("{")
```

The parser pushes an object frame:

```text
stack:
    root object
```

The object frame tracks:

```text
schema
seen properties
current property
current parsing phase
```

### 6. Continue property parsing

After `{`, the parser allows a quoted property name.

The tokenizer index finds quote-starting candidates:

```text
"name"
"unknown"
```

The parser simulation rejects `"unknown"` because:

```python
additionalProperties == False
```

It accepts `"name"`.

Then the expected flow is:

```text
{
    -> "name"
    -> :
    -> "Ada"
    -> }
```

When `}` is tested, the parser checks:

```text
required properties seen?
```

Since `"name"` was seen, the object can complete.

## The Full Shared Flow

Both constraints follow the same decoder contract:

```text
constraint.bind(tokenizer)
        |
        v
TokenIndex decodes and indexes vocabulary once
        |
        v
 decoder asks constraint.valid_token_ids()
        |
        v
constraint asks its state machine for valid symbols
        |
        v
TokenIndex finds candidate token buckets
        |
        v
constraint simulates each full token
        |
        v
valid token IDs go to decoder
        |
        v
decoder masks logits
        |
        v
model selects one token ID
        |
        v
constraint.consume_token(token_id)
        |
        v
real DFA/parser state advances
        |
        v
constraint.is_complete()
```

## Important Correction to Your Mental Model

You said:

> before the decoder predicts a text, the tokenizer decodes the tokens and indexes them

Almost correct, but more precisely:

```text
Before generation:
    tokenizer vocabulary is decoded once and indexed.

At each generation step:
    the constraint asks the index for likely candidates.
    candidate token text is simulated against the state machine.
    valid token IDs are passed to the decoder.

During model prediction:
    the model predicts token IDs, not text.

After prediction:
    the selected token ID is decoded from the cache and committed.
```

The tokenizer does not repeatedly decode every token before every prediction. That was the original expensive approach. `TokenIndex` avoids that repeated work.
