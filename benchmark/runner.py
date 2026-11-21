"""Benchmark runner strategies.

Each strategy function takes a Task, a Decoder, and run parameters.
It returns a single observation dict ready for JSONL serialisation.

All three strategies use the same _validate() helper so that validity
is judged by identical code regardless of how the output was produced.

Timing boundaries
-----------------
latency_s
    Generation only: perf_counter() immediately before and after
    decoder.generate(). For retry, this is the sum across all attempts.
    For constrained generation it includes constraint.bind(), because that
    happens inside generate(), but excludes constraint construction.

validation_time_s
    Time spent inside _validate(). For retry, this is the sum across all
    attempts. Excluded from latency_s.

e2e_latency_s
    The complete strategy operation: setup/seeding, constraint construction
    (Approach C only), every generation attempt, every validation, and retry
    loop overhead. This is intentionally larger than
    latency_s + validation_time_s because it also includes setup and control
    flow.

bind_time_s, valid_token_ids_time_s, consume_token_time_s
    Measured internally by decoder.generate() via the _metrics dict.
    Zero for unconstrained approaches (normal and retry).
"""

import json
import time

import jsonschema
import torch

from benchmark.dataset import Task
from tcd import JSONSchemaConstraint

# ---------------------------------------------------------------------------
# Shared validation helper
# ---------------------------------------------------------------------------

def _validate(output: str, schema: dict) -> tuple[bool, bool]:
    """Return (valid_json, valid_schema) for a raw generation output.

    Two distinct failure modes are distinguished:

    valid_json=False
        json.loads() raised an exception. The output is not syntactically
        valid JSON at all.

    valid_json=True, valid_schema=False
        The output parsed as JSON but does not satisfy the schema.

    Both flags are False when JSON parsing fails because schema validation
    cannot be attempted on a string that is not valid JSON.

    Parameters
    ----------
    output
        Raw string returned by decoder.generate().
    schema
        JSON Schema dict to validate the parsed output against.

    Returns
    -------
    tuple[bool, bool]
        (valid_json, valid_schema)
    """
    try:
        parsed = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return False, False

    try:
        jsonschema.validate(instance=parsed, schema=schema)
    except jsonschema.ValidationError:
        return True, False

    return True, True


# ---------------------------------------------------------------------------
# Approach A — normal prompting
# ---------------------------------------------------------------------------

def run_normal(
    task: Task,
    decoder,
    *,
    prompt: str | None = None,
    run_index: int,
    seed: int,
    max_tokens: int = 100,
    temperature: float = 0.8,
) -> dict:
    """Run Approach A: single unconstrained generation, no retry.

    The model receives the task prompt and generates freely. Output is
    validated after the fact. No retry is attempted regardless of validity.

    Parameters
    ----------
    task
        Benchmark task supplying the prompt and schema.
    decoder
        Loaded decoder instance. Must expose a generate() method with the
        same signature as tcd.Decoder.generate().
    prompt
        Prompt to send to the decoder. Defaults to ``task.prompt``.
    run_index
        Repetition index recorded in the result for traceability.
    seed
        PyTorch random seed applied before generation so that runs are
        individually reproducible.
    max_tokens
        Maximum new tokens to generate.
    temperature
        Sampling temperature.

    Returns
    -------
    dict
        One observation with all measurement fields populated.
    """
    prompt = task.prompt if prompt is None else prompt
    e2e_start = time.perf_counter()
    torch.manual_seed(seed)

    metrics = {}
    start = time.perf_counter()
    output = decoder.generate(
        prompt,
        constraint=None,
        max_tokens=max_tokens,
        temperature=temperature,
        _metrics=metrics,
    )
    latency_s = time.perf_counter() - start

    validation_start = time.perf_counter()
    valid_json, valid_schema = _validate(output, task.schema)
    validation_time_s = time.perf_counter() - validation_start
    e2e_latency_s = time.perf_counter() - e2e_start
    finish_reason = metrics["finish_reason"]

    return {
        "approach": "normal",
        "task_id": task.task_id,
        "run_index": run_index,
        "seed": seed,
        "output": output,
        "tokens_generated": metrics["tokens_generated"],
        "latency_s": latency_s,
        "validation_time_s": validation_time_s,
        "e2e_latency_s": e2e_latency_s,
        "valid_json": valid_json,
        "valid_schema": valid_schema,
        "finish_reason": finish_reason,
        "truncated": finish_reason == "max_tokens",
        "retries": 0,
        "exhausted_retries": False,
        "bind_time_s": metrics["bind_time_s"],
        "valid_token_ids_time_s": metrics["valid_token_ids_time_s"],
        "consume_token_time_s": metrics["consume_token_time_s"],
    }


# ---------------------------------------------------------------------------
# Approach B — prompting with validation and retry
# ---------------------------------------------------------------------------

def run_retry(
    task: Task,
    decoder,
    *,
    prompt: str | None = None,
    run_index: int,
    seed: int,
    max_retries: int = 3,
    max_tokens: int = 100,
    temperature: float = 0.8,
) -> dict:
    """Run Approach B: unconstrained generation with validation and retry.

    Generates up to ``max_retries + 1`` times. Each attempt uses a derived
    seed (``seed + attempt``) so that retries produce different outputs while
    remaining individually reproducible.

    ``tokens_generated`` and ``latency_s`` are totals across all attempts.
    This reflects the true computational cost of the retry strategy: if three
    attempts were needed, all three contribute to the reported numbers.

    Parameters
    ----------
    task
        Benchmark task supplying the prompt and schema.
    decoder
        Loaded decoder instance.
    prompt
        Prompt to send to the decoder. Defaults to ``task.prompt``.
    run_index
        Repetition index recorded in the result for traceability.
    seed
        Base PyTorch random seed. Attempt ``k`` uses ``seed + k``.
    max_retries
        Maximum number of additional attempts after the first.
        Total attempts = ``max_retries + 1``.
    max_tokens
        Maximum new tokens per attempt.
    temperature
        Sampling temperature.

    Returns
    -------
    dict
        One observation. ``retries`` counts attempts after the first.
        ``exhausted_retries`` is True when all attempts failed.
        ``tokens_generated``, ``latency_s``, and ``validation_time_s`` are
        totals across all attempts. ``e2e_latency_s`` spans the entire
        strategy call, including setup and loop overhead.
    """
    prompt = task.prompt if prompt is None else prompt
    e2e_start = time.perf_counter()
    total_tokens = 0
    total_latency_s = 0.0
    total_validation_s = 0.0
    output = ""
    valid_json = False
    valid_schema = False
    finish_reason = "max_tokens"
    attempt = 0

    for attempt in range(max_retries + 1):
        torch.manual_seed(seed + attempt)

        metrics = {}
        start = time.perf_counter()
        output = decoder.generate(
            prompt,
            constraint=None,
            max_tokens=max_tokens,
            temperature=temperature,
            _metrics=metrics,
        )
        total_latency_s += time.perf_counter() - start
        total_tokens += metrics["tokens_generated"]
        finish_reason = metrics["finish_reason"]

        validation_start = time.perf_counter()
        valid_json, valid_schema = _validate(output, task.schema)
        total_validation_s += time.perf_counter() - validation_start

        if valid_json and valid_schema:
            break

    e2e_latency_s = time.perf_counter() - e2e_start

    return {
        "approach": "retry",
        "task_id": task.task_id,
        "run_index": run_index,
        "seed": seed,
        "output": output,
        "tokens_generated": total_tokens,
        "latency_s": total_latency_s,
        "validation_time_s": total_validation_s,
        "e2e_latency_s": e2e_latency_s,
        "valid_json": valid_json,
        "valid_schema": valid_schema,
        "finish_reason": finish_reason,
        "truncated": finish_reason == "max_tokens",
        "retries": attempt,
        "exhausted_retries": not (valid_json and valid_schema),
        "bind_time_s": 0.0,
        "valid_token_ids_time_s": 0.0,
        "consume_token_time_s": 0.0,
    }


# ---------------------------------------------------------------------------
# Approach C — TCD constrained decoding
# ---------------------------------------------------------------------------

def run_constrained(
    task: Task,
    decoder,
    *,
    prompt: str | None = None,
    run_index: int,
    seed: int,
    max_tokens: int = 100,
    temperature: float = 0.8,
) -> dict:
    """Run Approach C: TCD JSON Schema constrained generation.

    A fresh JSONSchemaConstraint is created from the task schema before each
    call. Constraint creation (compile_schema + initial parser state) is fast
    and happens outside the latency timer. The expensive cost — TokenIndex
    construction over the full vocabulary — happens inside generate() and is
    captured in bind_time_s.

    _validate() is still applied to the output even though TCD enforces
    structural validity by construction. The one case where output may be
    invalid is when max_tokens is reached before the constraint completes,
    producing a truncated JSON string.

    Parameters
    ----------
    task
        Benchmark task supplying the prompt and schema.
    decoder
        Loaded decoder instance.
    prompt
        Prompt to send to the decoder. Defaults to ``task.prompt``.
    run_index
        Repetition index recorded in the result for traceability.
    seed
        PyTorch random seed applied before generation.
    max_tokens
        Maximum new tokens to generate. If the constraint does not complete
        within this budget, the output will be truncated and invalid.
    temperature
        Sampling temperature.

    Returns
    -------
    dict
        One observation. bind_time_s, valid_token_ids_time_s, and
        consume_token_time_s are populated from decoder._metrics and will
        be non-zero for a constrained generation. ``e2e_latency_s`` includes
        constraint construction, generation, and validation.
    """
    prompt = task.prompt if prompt is None else prompt
    e2e_start = time.perf_counter()
    constraint = JSONSchemaConstraint(task.schema)
    torch.manual_seed(seed)

    metrics = {}
    start = time.perf_counter()
    output = decoder.generate(
        prompt,
        constraint=constraint,
        max_tokens=max_tokens,
        temperature=temperature,
        _metrics=metrics,
    )
    latency_s = time.perf_counter() - start

    validation_start = time.perf_counter()
    valid_json, valid_schema = _validate(output, task.schema)
    validation_time_s = time.perf_counter() - validation_start
    e2e_latency_s = time.perf_counter() - e2e_start
    finish_reason = metrics["finish_reason"]

    return {
        "approach": "constrained",
        "task_id": task.task_id,
        "run_index": run_index,
        "seed": seed,
        "output": output,
        "tokens_generated": metrics["tokens_generated"],
        "latency_s": latency_s,
        "validation_time_s": validation_time_s,
        "e2e_latency_s": e2e_latency_s,
        "valid_json": valid_json,
        "valid_schema": valid_schema,
        "finish_reason": finish_reason,
        "truncated": finish_reason == "max_tokens",
        "retries": 0,
        "exhausted_retries": False,
        "bind_time_s": metrics["bind_time_s"],
        "valid_token_ids_time_s": metrics["valid_token_ids_time_s"],
        "consume_token_time_s": metrics["consume_token_time_s"],
    }
