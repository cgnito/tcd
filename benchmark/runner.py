"""Benchmark runner strategies.

Each strategy function takes a Task, a Decoder, and run parameters.
It returns a single observation dict ready for JSONL serialisation.

All three strategies use the same _validate() helper so that validity
is judged by identical code regardless of how the output was produced.

Timing boundaries
-----------------
latency_s
    Measured externally: perf_counter() before and after decoder.generate().
    Includes everything the caller experiences.

bind_time_s, valid_token_ids_time_s, consume_token_time_s
    Measured internally by decoder.generate() via the _metrics dict.
    Zero for unconstrained approaches (normal and retry).
"""

import json
import time

import jsonschema
import torch

from benchmark.dataset import Task


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
    torch.manual_seed(seed)

    metrics = {}
    start = time.perf_counter()
    output = decoder.generate(
        task.prompt,
        constraint=None,
        max_tokens=max_tokens,
        temperature=temperature,
        _metrics=metrics,
    )
    latency_s = time.perf_counter() - start

    valid_json, valid_schema = _validate(output, task.schema)

    return {
        "approach": "normal",
        "task_id": task.task_id,
        "run_index": run_index,
        "seed": seed,
        "output": output,
        "tokens_generated": metrics["tokens_generated"],
        "latency_s": latency_s,
        "valid_json": valid_json,
        "valid_schema": valid_schema,
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
        ``tokens_generated`` and ``latency_s`` are totals across all
        attempts.
    """
    total_tokens = 0
    total_latency_s = 0.0
    output = ""
    valid_json = False
    valid_schema = False
    attempt = 0

    for attempt in range(max_retries + 1):
        torch.manual_seed(seed + attempt)

        metrics = {}
        start = time.perf_counter()
        output = decoder.generate(
            task.prompt,
            constraint=None,
            max_tokens=max_tokens,
            temperature=temperature,
            _metrics=metrics,
        )
        total_latency_s += time.perf_counter() - start
        total_tokens += metrics["tokens_generated"]

        valid_json, valid_schema = _validate(output, task.schema)
        if valid_json and valid_schema:
            break

    return {
        "approach": "retry",
        "task_id": task.task_id,
        "run_index": run_index,
        "seed": seed,
        "output": output,
        "tokens_generated": total_tokens,
        "latency_s": total_latency_s,
        "valid_json": valid_json,
        "valid_schema": valid_schema,
        "retries": attempt,
        "exhausted_retries": not (valid_json and valid_schema),
        "bind_time_s": 0.0,
        "valid_token_ids_time_s": 0.0,
        "consume_token_time_s": 0.0,
    }
