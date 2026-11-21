# Benchmarking

This document describes the exploratory benchmark included with TCD, the published results, and the limitations that should be kept in mind when reading them.

The benchmark asks a narrow question:

> On a small set of JSON-generation tasks, how do normal prompting, validation with retries, and TCD constrained decoding compare on schema validity, generated tokens, and latency?

It is a demonstration of behaviour, not a statistically powered evaluation.

## The three approaches

### Approach A: normal prompting

Generate once with no constraint and validate afterward. This is the baseline: one model call sequence, no retries, no constraint overhead.

### Approach B: validation and retries

Generate, validate, and retry up to three times (four attempts total) with different seeds. The result records the final attempt and the total generation cost across all attempts. This represents the common “ask again if invalid” workflow.

### Approach C: constrained decoding

Generate with a `JSONSchemaConstraint`. Invalid token IDs are masked before sampling. A fresh constraint is created for every run, and `bind()` builds a new `TokenIndex` for the tokenizer. That binding cost is included in the measured generation latency.

The three approaches are intended to answer different practical questions:

- A: what does the model do with no structural enforcement?
- B: can post-hoc validation and retries recover from invalid output?
- C: what does it cost to enforce the schema during generation?

## Tasks

The dataset contains five tasks with increasing structural complexity. All three approaches receive the same prompt and are validated against the same schema.

| Task | Structure | What it exercises |
|---|---|---|
| TC-1 | Flat object, two string fields | Minimal baseline. |
| TC-2 | Flat object, string/integer/boolean | Mixed primitive types. |
| TC-3 | Flat object with bounded integers | Numeric constraints and four fields. |
| TC-4 | Nested object plus string field | Parser stack depth and nested closing. |
| TC-5 | Array of objects | Array handling and the longest outputs. |

Prompts describe the required fields in prose and ask for only the JSON value. The schemas are not embedded in the prompt.

## Configuration

The published run is `20261121T113832270267Z`.

| Setting | Value |
|---|---|
| Model | `Qwen/Qwen2.5-0.5B-Instruct` |
| Runs per task | 5 |
| Tasks | 5 |
| Observations per approach | 25 |
| Maximum new tokens | 100 |
| Temperature | 0.8 |
| Retries in Approach B | 3 |
| Retry attempts total | 4 |
| Seed base | 0 |
| Seed spacing | 100 |
| Prompt format | Qwen chat template |
| Device | CPU |

Environment recorded in the metadata:

- Python 3.13.14
- PyTorch 2.14.0+cpu
- Transformers 5.17.0
- jsonschema 4.26.0
- Linux on WSL2, x86_64
- Intel Core i7-8650U, 8 logical CPUs
- Approximately 7.7 GiB RAM

## Prompt formatting

The benchmark formats each task prompt as a single user message with the tokenizer's chat template:

```python
tokenizer.apply_chat_template(
    [{"role": "user", "content": prompt}],
    tokenize=False,
    add_generation_prompt=True,
)
```

The rendered prompt is passed to the decoder as a string. The same rendered prompt is used for all three approaches and for the warm-up. Qwen's template includes its default system message.

The raw task prompt and the rendered prompt are both stored in the metadata. No additional system prompt or JSON-specific instruction was added, so the comparison does not introduce a prompt advantage for any approach.

## Seeds and run order

For run index `i`, the base seed is:

```text
seed = seed_base + i * 100
```

The spacing leaves room for retry seeds. Approach A and C use the base seed. Approach B attempt `k` uses `seed + k`.

The loop is run-major:

```text
for run_index:
    for task:
        for approach in (normal, retry, constrained):
```

This spreads any slow drift in CPU performance across tasks rather than concentrating it in one task. A warm-up runs both unconstrained and constrained generation before any observation is recorded; the warm-up is untimed.

## Validation protocol

The primary results use strict validation:

1. Parse the raw output with `json.loads`.
2. Validate the parsed value with `jsonschema.validate` against the task schema.

No normalization is applied. In particular, Markdown code fences are **not** stripped. A response such as:

````text
```json
{"name": "Ada", "status": "active"}
```
````

is recorded as invalid JSON under the primary protocol.

The two validation flags are independent:

- `valid_json`: the raw response parsed as JSON.
- `valid_schema`: the parsed value also satisfied the schema.

An output can be valid JSON but schema-invalid. An output that is not valid JSON cannot be schema-valid.

The fence-stripped analysis later in this document is explicitly post-hoc and does not change the primary observations.

## Metrics

### Latency

`latency_s` measures generation only:

- It starts immediately before `decoder.generate()`.
- It ends immediately after `decoder.generate()`.
- For Approach B, it is the sum across all attempts.
- For Approach C, it includes `constraint.bind()` because binding happens inside `generate()`, but excludes constraint construction.

`validation_time_s` measures the validation calls and is kept separate from generation latency.

`e2e_latency_s` covers the whole strategy call: setup, seeding, constraint construction for C, all generation attempts, all validation, and retry-loop overhead.

### Constraint timings

The decoder can populate an optional `_metrics` dictionary with:

- `bind_time_s`: time spent in `constraint.bind()`.
- `valid_token_ids_time_s`: time spent asking the constraint for valid IDs.
- `consume_token_time_s`: time spent committing sampled tokens.
- `tokens_generated`: generated token count.
- `finish_reason`: `constraint_complete`, `eos`, or `max_tokens`.

These fields are zero for unconstrained approaches.

### Tokens and throughput

`tokens_generated` counts generated tokens, not prompt tokens. For Approach B it includes every attempt, not only the final one.

The aggregate throughput figure is:

```text
total generated tokens / total generation latency
```

so it reflects the effective cost of the strategy, including retries and truncated constrained runs.

## Results

### Overall

| Approach | Schema-valid | JSON-valid | Truncated | Retries | Mean latency | Median latency | Mean tokens | Tokens/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Normal | 7/25 (28%) | 8/25 (32%) | 0 | 0 | 9.21s | 9.39s | 35.9 | 3.90 |
| Retry | 10/25 (40%) | 10/25 (40%) | 0 | 48 | 25.12s | 25.08s | 111.9 | 4.45 |
| Constrained | 19/25 (76%) | 19/25 (76%) | 6 | 0 | 27.86s | 17.84s | 42.6 | 1.53 |

The strict result favours constrained decoding on validity, but at a higher average latency and lower throughput. The median constrained latency is lower than the mean because six runs hit the token limit and inflate the mean.

### Per task

| Task | Approach | Schema-valid | Mean latency | Mean tokens | Truncated |
|---|---|---:|---:|---:|---:|
| TC-1 | Normal | 2/5 | 6.46s | 20.4 | 0 |
| TC-1 | Retry | 3/5 | 12.92s | 50.0 | 0 |
| TC-1 | Constrained | 5/5 | 11.80s | 16.0 | 0 |
| TC-2 | Normal | 2/5 | 8.17s | 29.4 | 0 |
| TC-2 | Retry | 3/5 | 16.64s | 71.8 | 0 |
| TC-2 | Constrained | 5/5 | 14.53s | 23.6 | 0 |
| TC-3 | Normal | 1/5 | 10.14s | 39.0 | 0 |
| TC-3 | Retry | 2/5 | 28.53s | 120.2 | 0 |
| TC-3 | Constrained | 3/5 | 38.19s | 59.0 | 2 |
| TC-4 | Normal | 2/5 | 9.86s | 38.8 | 0 |
| TC-4 | Retry | 2/5 | 27.30s | 110.6 | 0 |
| TC-4 | Constrained | 2/5 | 45.82s | 72.6 | 3 |
| TC-5 | Normal | 0/5 | 11.41s | 51.8 | 0 |
| TC-5 | Retry | 0/5 | 40.24s | 207.0 | 0 |
| TC-5 | Constrained | 4/5 | 28.96s | 42.0 | 1 |

Constrained decoding is most reliable on the simpler object tasks. Its failures concentrate on the nested object and bounded-integer tasks, where it sometimes spends the entire 100-token budget before completing the schema.

### Primary failure modes

| Approach | Invalid JSON | Schema-invalid JSON | Errors | Fenced output |
|---|---:|---:|---:|---:|
| Normal | 17 | 1 | 0 | 17 |
| Retry | 15 | 0 | 0 | 15 |
| Constrained | 6 | 0 | 0 | 0 |

No run raised an exception. All constrained failures were truncated outputs, not completed outputs that violated the schema.

The dominant unconstrained failure was not malformed JSON logic. It was formatting: the model usually generated a valid JSON object inside a Markdown code fence despite the instruction to return only the JSON value. Strict validation rejects that output.

Approach B spent 48 retries to improve from 7/25 to 10/25 under strict validation. Many retries regenerated the same fenced format, so retrying alone did not reliably fix the problem.

## Fence-stripped sensitivity analysis

This analysis is **post-hoc only**. It does not alter the primary results.

For each invalid output, the analyzer checks whether the entire output is a Markdown code fence containing a JSON value. If so, it strips the fence, parses the inner text, and re-validates it against the same schema.

| Approach | Fenced invalid | Recovered | Still invalid JSON | Still schema-invalid | Lenient valid |
|---|---:|---:|---:|---:|---:|
| Normal | 17 | 16 | 0 | 1 | 23/25 (92%) |
| Retry | 15 | 14 | 0 | 1 | 24/25 (96%) |
| Constrained | 0 | 0 | 0 | 0 | 19/25 (76%) |

Under this sensitivity analysis, normal and retry prompting are more schema-valid than constrained decoding. This is the most important caveat in the benchmark: TCD's strict-validation advantage is largely about producing **pure JSON without Markdown formatting**, not about fixing every semantic schema error.

The two remaining fenced failures after stripping were schema-invalid, not JSON syntax failures.

## Interpretation

What the experiment supports:

- On these tasks, unconstrained Qwen often wraps otherwise valid JSON in Markdown fences.
- Strict validation therefore penalizes unconstrained generation heavily.
- Retrying without changing the prompt or format is a costly way to handle this failure mode.
- In this run, every constrained output that completed within the token budget was schema-valid.
- Constrained decoding can be slower and can truncate on more complex schemas.

What the experiment does **not** support:

- A general claim that TCD is more accurate than prompting across models or tasks.
- A claim that TCD is faster; it is not faster in this run.
- A claim that TCD guarantees completion. Six constrained runs truncated at 100 tokens.
- A claim of statistical significance. There are only 25 observations per approach.

## Reproduction

From the repository root:

```bash
uv sync
uv run python -m benchmark.run_benchmark
uv run python -m benchmark.analyze
```

The run writes a new timestamped metadata file and JSONL observation file under `benchmark/results/`. Generated runs are ignored by Git; the published run is tracked under `benchmark/results/published/`.

To analyze the published run explicitly:

```bash
uv run python -m benchmark.analyze \
  benchmark/results/published/20261121T113832270267Z_observations.jsonl
```

The analyzer infers the matching metadata file by filename, prints aggregate and per-task tables, and reports both primary failure modes and fence sensitivity.

## Published files

- [`benchmark/results/published/20261121T113832270267Z_metadata.json`](../benchmark/results/published/20261121T113832270267Z_metadata.json)
- [`benchmark/results/published/20261121T113832270267Z_observations.jsonl`](../benchmark/results/published/20261121T113832270267Z_observations.jsonl)

The metadata records the model, environment, generation settings, task schemas, raw prompts, and rendered chat prompts. The JSONL contains one observation per line with the raw output, validation flags, generation metrics, and retry count.

## Limitations and threats to validity

### Sample size

Five runs per task and 25 observations per approach are enough for a demonstration, not for confidence intervals or significance testing. A different seed set could change individual task results.

### One model and one environment

The results come from one 0.5B instruction model on one CPU. Model size, instruction tuning, tokenizer design, and hardware can all change the balance between approaches.

### Strict validation is a choice

Treating fenced JSON as invalid is defensible when the prompt asks for only the JSON value, but it is not the only possible evaluation rule. The sensitivity analysis exists because this choice materially changes the conclusion.

### Prompt formatting

The benchmark uses Qwen's chat template with its default system message. Raw prompting produced different formatting behaviour in earlier development runs. The published run does not compare raw and chat-formatted prompting.

### Token limit

The 100-token limit is binding for some constrained runs. Raising it might improve constrained validity but would increase latency and change the experiment.

### Timing scope

Latency includes model generation and, for Approach C, per-call constraint binding. It does not include model download, model loading, or measurement of final output quality. The benchmark runs on CPU, so GPU timings would differ.

### Local constraints

TCD validates the next token, not the existence of a complete valid continuation. A run can be locally valid and still fail to finish. This is a property of the implementation, not a measurement artifact.

### Tokenizer assumptions

`TokenIndex` decodes tokens individually. Byte-level or context-sensitive tokenizers may not behave exactly like the tokenizer used here.
