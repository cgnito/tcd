# tcd — learning and building plan

this is my personal learning and building plan for tcd.

the goal is not just to build a constrained decoder, but to understand the ideas behind it deeply enough that i can explain why each part exists and how it works.

---

## phase 0 — establish the mental model

**status:**  ✔️done✔️

### question

**how does an autoregressive llm generate text?**

### learn

* [x] token
* [x] tokenizer
* [x] vocabulary
* [x] token ids
* [x] logits
* [x] softmax
* [x] probability distribution
* [x] sampling
* [x] temperature
* [x] autoregressive generation

you do **not** need to understand the ml mathematics deeply yet.

you need to understand this:

```text
"the capital of france is"

        ↓ model

token probabilities:

paris     0.71
london    0.09
lyon      0.04
...
```

then:

```text
choose token
     ↓
append token
     ↓
run model again
     ↓
choose next token
```

### build

don't use `model.generate()`.

load a small hugging face model and manually generate **one token**.

then manually generate 20 tokens using a loop.

something conceptually like:

```text
for _ in range(20):

    logits = model(tokens)

    next_token_logits = logits[-1]

    probs = softmax(next_token_logits)

    next_token = sample(probs)

    tokens.append(next_token)
```

### done when

* [x] i can manually generate one token from an llm
* [x] i can manually generate multiple tokens in a loop
* [x] i understand what logits represent
* [x] i understand why generation is autoregressive
* [x] i can explain the generation loop without looking it up

when you successfully do this, you have crossed the first major threshold.

because now **you control generation.**

---

# phase 1 — build the unconstrained decoder

**status:** ▶️started▶️

refactor that ugly generation loop into your own:

```text
decoder
```

support:

```text
decoder.generate(
    prompt,
    max_tokens=50,
    temperature=0.8
)
```

### learn

* [x] greedy decoding
* [x] multinomial sampling
* [x] temperature
* [x] eos tokens

build those yourself.

now you've essentially built a miniature version of a tiny part of hugging face's `.generate()`.

that's important because later you'll intercept this process.

### done when

* [x] i have my own `decoder`
* [x] i can generate using greedy decoding
* [x] i can generate using sampling
* [x] temperature works
* [x] generation stops at an eos token
* [ ] i understand where i will eventually apply constraints

---

# phase 2 — your first constraint

**status:** ⬜ not started

now implement:

```text
choice(["yes", "no"])
```

at each generation step:

```text
model logits

    ↓

which tokens can still lead to:
yes
or
no?

    ↓

mask every other token

    ↓

sample
```

this is your first real constrained decoder.

at the end of this phase, your demo should show:

```text
without constraint

"yes, i believe paris definitely..."
```

versus:

```text
with constraint

"yes"
```

and you should be able to explain **why invalid output is impossible**.

### done when

* [ ] i can define a set of allowed outputs
* [ ] i can determine which tokens are allowed
* [ ] i can mask invalid tokens
* [ ] masked tokens cannot be sampled
* [ ] `choice(["yes", "no"])` works
* [ ] i can explain why this is different from validation after generation

---

# phase 3 — understand tokenization properly

**status:** ⬜ not started

this phase will probably humble you a little.

run experiments.

inspect:

```text
tokenizer.encode("yes")
tokenizer.encode(" yes")
tokenizer.encode("yesterday")
tokenizer.encode("{")
tokenizer.encode('{"name":')
```

you'll discover that:

```text
characters != tokens
words != tokens
```

and that seemingly simple prefix matching gets complicated.

### learn

* [ ] bpe / tokenizer basics
* [ ] vocabulary
* [ ] token prefixes
* [ ] special tokens

then modify your `choice` constraint so it operates correctly at the token level.

### done when

* [ ] i understand how my chosen tokenizer represents text
* [ ] i understand why one word can become multiple tokens
* [ ] i understand why a token can contain a space or partial word
* [ ] my `choice` constraint works correctly with tokenization
* [ ] i can explain why character-level matching is not enough

this phase will give me a much stronger understanding of llm inference than simply calling apis.

---

# phase 4 — state machines

**status:** ⬜ not started

now you're ready for theory.

### learn

* [ ] state
* [ ] transition
* [ ] start state
* [ ] accepting state
* [ ] deterministic finite automaton
* [ ] regex → automaton conceptually

you can represent:

```text
yes|no
```

as:

```text
          y → e → s → accept
        /
start
        \
          n → o → accept
```

then your decoder's question becomes:

> given my current state, which token transitions keep me in a valid state?

that is much more general than manually checking strings.

### build

```text
regexconstraint(...)
```

start extremely simple.

don't implement pcre.

support a tiny subset.

### done when

* [ ] i understand what a state is
* [ ] i understand what a transition is
* [ ] i understand accepting states
* [ ] i understand the basic idea of a dfa
* [ ] i can represent a simple regex as a state machine
* [ ] my decoder can use a state machine as a constraint
* [ ] `regexconstraint(...)` works for a small regex subset

---

# phase 5 — constrained token indexing

**status:** ⬜ not started

this is where things start becoming legitimately interesting.

naively, at every step you could ask:

```text
for every token in vocabulary:

    append token

    check whether result remains valid
```

if your vocabulary has:

```text
50,000 tokens
```

that's expensive.

now you start asking:

> **can i precompute which tokens are valid from each state?**

conceptually:

```text
state 0
   ↓
allowed token ids:
[45, 492, 3819, ...]
```

you are now moving toward the kind of optimization structured-generation libraries care about.

outlines-core exists partly to make these lower-level operations faster and more portable; its rust implementation was introduced with reported speed improvements for index compilation.

now you can understand *why rust appears in their stack.*

it's no longer:

> "rust is fast."

it's:

> "this particular component may evaluate enormous numbers of tokenizer/state combinations, so a fast systems implementation matters."

that's much better understanding.

### build

* [ ] implement a naive token/state lookup
* [ ] measure its performance
* [ ] identify the expensive part
* [ ] precompute valid token ids for states
* [ ] compare the optimized version with the naive version

### done when

* [ ] i understand why checking every vocabulary token is expensive
* [ ] i understand what a token index represents
* [ ] i can precompute valid token ids for a state
* [ ] i can measure the performance difference
* [ ] i understand why a lower-level implementation can matter here

---

# phase 6 — json grammar

**status:** ⬜ not started

only now.

### learn

* [ ] grammar
* [ ] terminal
* [ ] non-terminal
* [ ] production rule
* [ ] context-free grammar
* [ ] parser basics

then write a simplified json grammar:

```text
value :=
    string
  | number
  | boolean
  | object
  | array
```

your first version can be intentionally limited.

maybe only:

```text
{
  "name": "string",
  "age": 18
}
```

no nested arrays.

no escaping madness.

then expand.

at this stage you'll start reading `outlines-core` and actually understanding what you're looking at instead of staring at alien code.

### done when

* [ ] i understand the basic components of a grammar
* [ ] i can define a small json grammar
* [ ] i can represent grammar states
* [ ] i can determine valid next tokens from a grammar state
* [ ] my decoder can generate a constrained json object
* [ ] i can explain how grammar state affects token selection

---

# phase 7 — schemas

**status:** ⬜ not started

build:

```text
schema
   ↓
constraint representation
   ↓
decoder
```

maybe:

```text
schema = {
    "name": str,
    "age": int
}
```

eventually:

```text
pydantic
    ↓
json schema
    ↓
your grammar
```

you don't need full json schema compatibility.

document your supported subset.

that's good engineering.

### done when

* [ ] i can define a simple schema
* [ ] i can convert a schema into my constraint representation
* [ ] my decoder can generate output matching the schema
* [ ] i understand the relationship between schemas and grammars
* [ ] i document which schema features tcd supports
* [ ] unsupported schema features fail clearly

---

# phase 8 — benchmarking

**status:** ⬜ not started

now prove your thing works.

build a benchmark comparing:

```text
normal prompting

vs

prompt + validation + retry

vs

your constrained decoder
```

measure:

```text
valid outputs
invalid outputs
average retries
latency
tokens / second
constraint overhead
```

now your github repository stops looking like:

> "student toy."

and starts looking like:

> **engineering investigation.**

### done when

* [ ] i have a reproducible benchmark
* [ ] i measure validity
* [ ] i measure latency
* [ ] i measure tokens / second
* [ ] i measure constraint overhead
* [ ] i compare against validation + retry
* [ ] i document the results
* [ ] i can explain the tradeoffs of my approach

## project journey in one picture
```
┌────────────────────┐
│ HOW DOES AN LLM    │
│ GENERATE A TOKEN?  │
└─────────┬──────────┘
          ↓
Manual generation loop
          ↓
┌────────────────────┐
│ How do I stop it   │
│ choosing a token?  │
└─────────┬──────────┘
          ↓
    logits masking
          ↓
Choice["yes", "no"]
          ↓
┌────────────────────┐
│ How do strings map │
│ to model tokens?   │
└─────────┬──────────┘
          ↓
     tokenization
          ↓
multi-token choices
          ↓
┌────────────────────┐
│ How do I represent │
│ arbitrary rules?   │
└─────────┬──────────┘
          ↓
        FSM
          ↓
       regex
          ↓
┌────────────────────┐
│ How do I represent │
│ nested structures? │
└─────────┬──────────┘
          ↓
        CFG
          ↓
       JSON
          ↓
      schemas
          ↓
┌────────────────────┐
│ How do I make this │
│ actually fast?     │
└─────────┬──────────┘
          ↓
 precomputed indexes
          ↓
    benchmarking
---
```

# future phases

this plan is intentionally expandable.

when i understand the current phase well enough, i can add another phase below.

possible future areas:

```text
phase 9 — performance optimization

phase 10 — batching

phase 11 — caching

phase 12 — streaming

phase 13 — grammar compilation

phase 14 — rust implementation

phase 15 — integration with inference engines

phase 16 — production api

...
```

the goal is not to rush through the phases.

the goal is to **understand each layer, build it myself, and then move to the next layer.**
