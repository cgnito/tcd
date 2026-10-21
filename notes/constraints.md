## The constraint layer

The decoder generates **tokens**, but the DFA understands **characters**.

That means there is a gap between them:

```text
model vocabulary token
        |
        v
    decoded text
        |
        v
DFA consumes one character at a time
```

The constraint layer is the bridge between these two worlds.

It answers two questions:

1. which token IDs are legal from the DFA's current state?
2. after a token is generated, how does the DFA move through that token's text?

The main class for this is `DFAConstraint`.

## The public API

The decoder is now the only object a caller needs to use:

```python
from tcd import Decoder

decoder = Decoder()

response = decoder.generate(
    prompt="Is Python a programming language?",
    constraint="yes|no",
)
```

The caller provides a regex pattern as a string. `Decoder.generate()` creates
the DFA and the constraint internally:

```python
dfa = DFA(constraint_pattern)
constraint = DFAConstraint(dfa, self.tokenizer)
```

The caller does not need to know how the DFA or tokenizer vocabulary is
connected.

## What the DFA knows

For a pattern such as:

```text
yes|no
```

the DFA might have a shape like this:

```text
q0 --y--> q1 --e--> q2 --s--> q3 (accepting)
 |
 n
 v
q4 --o--> q5 (accepting)
```

The DFA works with one character at a time. From the start state `q0`, its
valid symbols are `y` and `n`.

`DFA.valid_symbols()` returns those outgoing symbols:

```python
valid_symbols = dfa.valid_symbols()
# {"y", "n"}
```

The DFA also owns the current state. Calling `transition()` checks a symbol
and moves the DFA to the next state:

```python
dfa.transition(dfa.current_state, "y")
```

## What the tokenizer knows

The language model does not choose characters directly. It chooses token IDs.
A token ID must be decoded before the DFA can understand it.

A tokenizer vocabulary could contain entries like these:

```text
id 0 -> "y"
id 1 -> "n"
id 2 -> "yes"
id 3 -> "no"
id 4 -> "yea"
```

A token can contain one character or many characters. This is important:
`"yes"` is one possible token, but it represents three DFA transitions:

```text
q0 --y--> q1 --e--> q2 --s--> q3
```

So checking only the first character is not enough. The entire decoded token
must be checked.

## Finding valid token IDs

`DFAConstraint.valid_token_ids()` returns token IDs that can be consumed from
the DFA's current state.

For every candidate token, the constraint simulates its decoded text without
changing the real DFA state:

```text
candidate token: "yes"
starting state: q0

try y -> q1
try e -> q2
try s -> q3

valid
```

An invalid candidate fails as soon as one character has no transition:

```text
candidate token: "yea"
starting state: q0

try y -> q1
try e -> q2
try a -> no transition

invalid
```

The simulation is separate from the real state update. Looking for candidates
must not move the DFA, because most candidates will be rejected and only one
will actually be generated.

## Why the old approach was expensive

The first implementation did this on every generation step:

```text
for every token in the vocabulary:
    decode the token
    check it against the DFA
```

If the vocabulary has `V` tokens and the decoder generates `N` tokens, this
repeats the vocabulary work roughly `N` times. It also decodes the same token
again and again.

That is wasteful because the tokenizer vocabulary does not change during a
single decoding session.

## The vocabulary index

`DFAConstraint` now builds an index once when it is created.

It decodes each vocabulary token once and groups the result by its first
character:

```text
"y" -> [(0, "y"), (2, "yes"), ...]
"n" -> [(1, "n"), (3, "no"), ...]
"e" -> [(5, "e"), ...]
```

It also keeps a cache from token ID to decoded text so that consuming a token
does not decode it again:

```text
0 -> "y"
1 -> "n"
2 -> "yes"
3 -> "no"
```

At generation time, the constraint now does this:

```text
DFA says the next symbols are {"y", "n"}
        |
        v
look only in the "y" and "n" buckets
        |
        v
simulate the full text of those candidates
        |
        v
return the valid token IDs
```

The full vocabulary is still decoded once while building the index. However,
that work is no longer repeated for every generated token. The hot path only
looks at buckets whose first character can possibly be accepted by the DFA.

## The decoder generation loop

For every generation step, `Decoder.generate()` follows this sequence:

```text
1. run the model and get next-token logits
2. ask the constraint for valid token IDs
3. mask every other token with negative infinity
4. convert the remaining logits into probabilities
5. sample one token ID
6. decode and consume that token through the DFA
7. stop if the DFA is accepting
8. otherwise run the model again with the new token
```

The masking happens before sampling. Therefore an invalid token has zero
probability and cannot be selected.

The important distinction is:

```text
validation after generation:
    generate first, reject later

constrained generation:
    reject invalid choices before sampling
```

## Committing the generated token

Candidate checking is only a simulation. Once the model selects a token, the
constraint commits it with `consume_token()`.

For a token whose decoded text is `"yes"`, commitment does this:

```python
for symbol in "yes":
    dfa.transition(dfa.current_state, symbol)
```

The DFA state changes only here, after a token has actually been selected.
That keeps the real DFA state synchronized with the generated response.

## Knowing when to stop

`DFAConstraint.is_complete()` checks whether the DFA's current state is an
accepting state:

```python
return dfa.current_state in dfa.accepting_states
```

For `yes|no`, after the decoder selects `"yes"`:

```text
q0 --y--> q1 --e--> q2 --s--> q3
                                      |
                                  accepting
```

The decoder stops immediately. It does not need to generate an EOS token to
finish the constrained result.

This is why EOS is not added to the constrained token list. The regex defines
what a complete answer is, and reaching an accepting DFA state is the correct
completion signal.

## Complete example

Suppose the pattern is:

```text
yes|no
```

The complete flow looks like this:

```text
Decoder.generate(..., constraint="yes|no")
        |
        v
create DFA("yes|no")
        |
        v
create DFAConstraint(dfa, tokenizer)
        |
        v
model produces logits
        |
        v
DFA is at q0, so inspect the "y" and "n" buckets
        |
        v
keep tokens such as "y", "n", "yes", and "no"
        |
        v
mask every other vocabulary ID
        |
        v
model samples "yes"
        |
        v
consume y, then e, then s
        |
        v
DFA reaches an accepting state
        |
        v
return "yes"
```

If the model instead selects `"y"`, the DFA moves to the state after `y`.
On the next step, the valid next symbol is `e`, so the constraint looks only
at tokens beginning with `e` and checks their complete text. The process
continues until a token reaches an accepting state or `max_tokens` is reached.

## Current tradeoffs and future work

The current optimization removes the repeated full-vocabulary scan from the
generation loop, but each new `DFAConstraint` still indexes the vocabulary once.
If many constraints use the same tokenizer, the index could be cached on the
`Decoder` or shared between constraints.

The current implementation also assumes that decoding one token in isolation
produces the text that should be checked by the DFA. That is a useful learning
implementation, but some tokenizers have byte-level or context-sensitive
behavior. Handling those cases correctly is a later tokenizer-focused problem.

For now, the important architecture is:

```text
regex pattern
    -> DFA
    -> valid character transitions
    -> indexed candidate token IDs
    -> logit mask
    -> sampled token
    -> committed DFA transitions
    -> accepting state or another generation step
```
