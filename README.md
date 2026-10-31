# TCD

Tiny Constrained Decoder (TCD) is a small Python implementation of
token-level constrained generation. It connects a language model tokenizer to
a regex-backed finite automaton so the decoder masks tokens that cannot lead to
a valid result.

## Motivation

I stumbled across [dottxt](https://dottxt.ai/) while looking for website
inspiration. I did not fully understand what the company was building, so I
started digging into its work, particularly
[Outlines](https://github.com/dottxt-ai/outlines), its library for generating
structured outputs from language models.

I wanted to understand constrained generation under the hood rather than only
use a library that handled it for me. That curiosity led me to build TCD from
scratch and explore regex parsing, finite automata, tokenization, and
token-level logit masking along the way.

TCD is under active development. I am continuing to improve the implementation,
connect the pieces into a more reliable decoder, and investigate how to make
constraint lookup more efficient.

## Quick Start

TCD requires Python 3.13 or newer. With [uv](https://docs.astral.sh/uv/)
installed:

```bash
uv sync
```

The first time `Decoder` is created, Transformers may download the configured
model and tokenizer from Hugging Face. The default model is
`Qwen/Qwen2.5-0.5B-Instruct`.

Run the interactive example:

```bash
uv run python examples/basic.py
```

Run the test suite without loading the real language model:

```bash
./scripts/test.sh
```

## Usage

The public entry point is `Decoder.generate()`. Pass a `RegexConstraint` as
the `constraint` argument:

```python
from tcd import Decoder, RegexConstraint

decoder = Decoder()

response = decoder.generate(
    prompt="Is Python a programming language?",
   constraint=RegexConstraint("yes|no"),
    max_tokens=10,
    temperature=0.8,
)

print(response)
```

For compatibility, a pattern string is also accepted and is converted to a
`RegexConstraint` internally:

```python
response = decoder.generate(
   prompt="Is Python a programming language?",
   constraint="yes|no",
)
```

During generation, TCD:

1. Builds a DFA from the constraint pattern.
2. Uses the tokenizer vocabulary to find token IDs whose decoded text can
   advance the DFA.
3. Masks all other logits before sampling.
4. Consumes the selected token through the DFA.
5. Stops when the DFA reaches an accepting state or `max_tokens` is reached.

The currently supported regex subset includes literals, concatenation,
alternation with `|`, grouping with parentheses, and repetition with `*`.
For example, `"red|blue|green"` allows one of three words, while
`"a(b|c)"` allows `ab` or `ac`.

The implementation is intentionally small and does not yet provide a general
JSON grammar, schema support, streaming, or a production inference backend.

The [`examples/experiments.py`](examples/experiments.py) script runs several
patterns through the public API. The [`notes/`](notes/) directory contains my
working explanations and learning notes for anyone who wants a glimpse of how
I understand the pieces as I build them.

## Contributing

TCD is an active investigation, so contributions that improve correctness,
clarity, tests, or measured performance are welcome.

Before opening a change:

1. Keep the implementation focused on the current supported regex subset.
2. Add or update tests under `tests/unit/`, `tests/integration/`, or
   `tests/e2e/` as appropriate.
3. Run the full suite:

   ```bash
   ./scripts/test.sh
   ```

4. Explain behavioral changes and performance claims with a reproducible
   example or measurement where possible.
