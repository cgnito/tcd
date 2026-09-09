# tcd

a tiny constrained decoder for llms.

its purpose is:

> **given an llm and a constraint describing valid outputs, generate text while preventing the model from selecting tokens that would make the output invalid.**

## why?

if you've worked with an ai api, you're essentially interacting with an llm: you send a request and get a response.

when that response is going to be used by software, you often need it to follow a specific format.

for example, maybe your application expects:

```json
{
  "name": "ayo",
  "amount": 1000000
}
```

but an llm might return:

```json
{
  "name": "ayo",
  "amount": "hundred thousand"
}
```

the output may look reasonable to a human, but your software expects `amount` to be a number, not a string.

you could generate the response, validate it, and if it's invalid, ask the llm to try again.

this is called **post-hoc validation**.

tcd takes a different approach.

## the idea

an llm generates text one token at a time.

at every step, the model produces probabilities for the possible next tokens:

```text
"yes"        0.4
"maybe"      0.2
"no"         0.1
"certainly"  0.05
...
```

normally, the model can choose from all of these tokens.

with constrained decoding, we define which choices are legal at that point in the generation.

for example, if a field can only be `"paid"` or `"pending"`, the decoder can block tokens that would lead to an invalid value.

conceptually:

```text
"paid"       allowed
"pending"    allowed
"cancelled"  blocked
"maybe"      blocked
```

the decoder then modifies the model's possible choices:

```text
"paid"       0.4
"pending"    0.2
"cancelled"  -∞
"maybe"      -∞
```

`-∞` means the model can no longer select that token.

so instead of:

```text
generate → validate → reject → retry
```

tcd does:

```text
generate → constrain → generate → constrain → ...
```

**the constraint is applied during generation, at every token.**

that's the core idea behind tcd.

## conceptual architecture: might change later
```
tcd/
│
├── src/
│   └── tcd/
│       ├── __init__.py
│       │
│       ├── model.py
│       ├── tokenizer.py
│       ├── decoder.py
│       ├── masking.py
│       ├── sampling.py
│       │
│       └── constraints/
│           ├── __init__.py
│           ├── choice.py
│           ├── regex.py
│           └── json.py
│
├── examples/
│   └── basic.py
│
├── tests/
│
├── benchmarks/
│
├── pyproject.toml
├── uv.lock
├── README.md
└── .gitignore
```
