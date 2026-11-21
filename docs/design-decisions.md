# Design Decisions

This document records engineering decisions that are easy to miss when reading the implementation. It focuses on correctness, state management, and performance trade-offs. For the generation loop and constraint internals, see [`architecture.md`](architecture.md).

## Parser states are cloned during candidate validation

The JSON parser is mutable. At each step, every candidate token must be tested against the current parser state, but only the sampled token may actually advance that state.

`JSONSchemaConstraint.valid_token_ids()` calls `JsonParserState.can_consume(text)` for each candidate. `can_consume()` must answer a hypothetical question:

> If this token were selected, would all of its characters be valid from the current state?

The parser therefore validates on a copy:

```python
candidate = self._clone()
for char in text:
    candidate._consume_char(char)
```

The live parser is unchanged unless `consume_token()` is called. This makes candidate validation non-destructive and keeps the constraint interface simple:

- `valid_token_ids()` is a query.
- `consume_token()` is a commit.

`consume()` also clones before applying text, but for a different reason: atomicity. If a token fails halfway through, the parser must not be left partially advanced. The clone is updated only after every character succeeds.

## A handwritten clone replaced deepcopy

The original implementation used `copy.deepcopy(self)` for candidate checks. That is correct but expensive.

The parser holds a reference to the compiled schema. The schema is a tree of frozen dataclasses, but `deepcopy` does not know that the tree is effectively immutable, so it walks and copies the whole structure for every candidate token. Candidate validation runs across the vocabulary at every step, so that cost dominates.

The replacement is `JsonParserState._clone()`:

```python
clone = object.__new__(JsonParserState)
clone._schema = self._schema
clone._stack = []
for frame in self._stack:
    copied = dict(frame)
    if "seen" in copied:
        copied["seen"] = set(copied["seen"])
    clone._stack.append(copied)
# copy the remaining scalar fields
```

The key observation is that only a few pieces of parser state are mutable:

- the stack list,
- each stack frame dictionary,
- the `seen` set inside object frames,
- scalar mode and buffer fields.

Schema nodes are frozen and can be shared. Strings are immutable. The handwritten clone copies the mutable containers and shares everything else.

The trade-off is maintenance cost: if a new mutable parser field is added later, `_clone()` must copy it. The test suite includes a differential test that compares the fast candidate checks against a `deepcopy` reference across a set of states and candidate texts, which helps catch regressions.

## String-content fast path

Most JSON candidate tokens during string content are ordinary characters. They append to the string buffer and cannot change parser mode, complete a value, or affect schema structure. For that case, `can_consume()` avoids cloning entirely:

```python
if (
    self._active_kind is not None
    and self._mode == "string"
    and not any(char in '"\\' or ord(char) < 0x20 for char in text)
):
    return True
```

The condition is deliberately narrow:

- there must be an active key or value,
- the parser must be in string mode,
- the text must not contain a quote, a backslash, or a control character.

A quote can close the string and trigger key/schema completion. A backslash starts an escape sequence. A control character is invalid in JSON string content. Those cases take the full clone-and-parse path.

The fast path does not bypass schema length checks. String `minLength` and `maxLength` are checked when the closing quote completes the value. It does mean that a token can append characters beyond `maxLength` and still be locally accepted; the eventual closing quote will then fail. This is consistent with TCD's local-validity model, which does not search ahead for a completion.

The benefit is large because candidate validation otherwise performs tens of thousands of parser copies per step. The differential test keeps the optimisation honest.

## EOS handling

Qwen models can expose more than one EOS token. In the model used for this project:

- the tokenizer's `eos_token_id` was `151645` (`<|im_end|>`),
- the model's generation configuration listed both `151645` and `151643` (`<|endoftext|>`).

The model emitted `151643`. Checking only `tokenizer.eos_token_id` missed it, so the token was decoded and appended as ordinary text before generation stopped. That produced corrupted output containing text after an EOS marker.

`Decoder._eos_token_ids()` collects EOS IDs from both sources:

```python
generation_config = getattr(self.model, "generation_config", None)
configured = getattr(generation_config, "eos_token_id", None)
# add int or all list entries
tokenizer_eos = getattr(self.tokenizer, "eos_token_id", None)
# add int
```

The generation loop checks EOS **before** decoding or appending the token:

```python
tokens_generated += 1
if constraint is None and next_token_id in eos_token_ids:
    finish_reason = "eos"
    break
```

Consequences:

- The EOS token counts as a generated token.
- Its decoded text is not included in the response.
- Any content generated before EOS is preserved.
- Constrained generation does not use EOS as a stop condition; it stops on constraint completion or the token limit.

The decision to exclude EOS text is important for the benchmark. Without it, a valid JSON object followed by `<|endoftext|>` and unrelated continuation text would be measured as invalid.

## Special tokens are excluded from constrained candidates

`TokenIndex` skips token IDs listed in `tokenizer.all_special_ids`:

```python
special_token_ids = set(getattr(tokenizer, "all_special_ids", ()) or ())
for token_id in tokenizer.get_vocab().values():
    if token_id in special_token_ids:
        continue
    ...
```

Without this filter, a special token could be treated as ordinary text. In constrained mode, `<|endoftext|>` could be accepted as valid string content because its decoded text is not a control character and does not break JSON syntax. That would let the model escape the constraint by emitting a special token.

The filter has two implications:

- Constrained generation cannot select EOS or other special tokens; completion must come from the constraint or the token limit.
- A tokenizer must expose `all_special_ids` for complete filtering. If it does not, the fallback is an empty set and the filter is inactive.

## TokenIndex caching and per-call binding

`TokenIndex` decodes the vocabulary once per `bind()` call and reuses the cached text for all candidate checks. It also groups tokens by first character to avoid scanning the entire vocabulary when the parser expects a specific symbol.

The index is not shared globally. Each `generate()` call binds the constraint to the tokenizer and builds a new index. In the benchmark, this cost is paid for every constrained run and is reported as `bind_time_s`.

This is a deliberate modelling choice: the benchmark represents a one-shot request where a constraint is created and used once. A long-running service could reuse a bound constraint or cache the index across requests, which would reduce per-request latency. The benchmark does not measure that optimisation.

Trade-offs:

- Caching trades memory for reduced repeated tokenizer decoding.
- First-character grouping speeds up structural states.
- Open string content still requires iterating all cached entries because almost any non-control character is valid.

## Local validity is the contract

TCD does not implement backtracking, lookahead, or a search for a complete valid continuation. A constraint answers:

> Is this token valid from the current state?

It does not answer:

> Does a complete valid document still exist if this token is chosen?

This contract keeps the implementation small and makes candidate checks local and fast. It also explains the observed failure modes:

- a valid prefix can run out of valid next tokens,
- a string can exceed `maxLength` and have no valid closing token,
- a constrained document can hit `max_tokens` before completion.

The decoder raises `ValueError` when no candidate token is valid and returns truncated output when the token limit is reached. Both are documented limitations, not hidden failure modes.

## Benchmark-only decisions

Two benchmark choices are intentionally separate from the core implementation:

- **Chat-template prompting:** formatting is done by the benchmark before calling `Decoder.generate()`, not inside the decoder. This keeps the core API text-in/text-out and makes the exact rendered prompt auditable.
- **Strict validation:** the primary benchmark rejects Markdown-fenced JSON because the prompts ask for only the JSON value. The fence-stripped analysis is post-hoc and reported separately.

See [`benchmarking.md`](benchmarking.md) for the experimental consequences.
