"""Run the TCD benchmark and write raw observations to JSONL.

Canonical invocation (from the project root)::

    uv run python -m benchmark.run_benchmark

The script loads the model once, runs an untimed warm-up, then executes all
three approaches across the benchmark tasks. Raw observations are written one
JSONL record per line and flushed immediately. Environment and configuration
metadata are written alongside the observations so a run can be interpreted
and reproduced later.

Aggregation is intentionally not done here.
"""

import json
import os
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import torch
import transformers

from benchmark.dataset import TASKS, Task
from benchmark.runner import run_constrained, run_normal, run_retry
from tcd import Decoder, JSONSchemaConstraint

MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"
RUNS_PER_TASK = 5
MAX_TOKENS = 100
TEMPERATURE = 0.8
MAX_RETRIES = 3
SEED_BASE = 0

APPROACHES = ("normal", "retry", "constrained")

RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# Configuration, metadata, and paths
# ---------------------------------------------------------------------------

def _seed_for_run(run_index: int, seed_base: int = SEED_BASE) -> int:
    """Return the base seed for one repetition.

    A spacing of 100 leaves room for retry seeds (``seed + attempt``) without
    colliding with the next run's base seed.
    """
    return seed_base + run_index * 100


def _make_run_id() -> str:
    """Return a UTC timestamp suitable for unique result filenames."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _result_paths(results_dir: Path, run_id: str) -> tuple[Path, Path]:
    """Return ``(metadata_path, observations_path)`` for one run."""
    return (
        results_dir / f"{run_id}_metadata.json",
        results_dir / f"{run_id}_observations.jsonl",
    )


def _package_version(name: str) -> str | None:
    """Return an installed package version, or None when unavailable."""
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _read_cpu_model() -> str:
    """Read the CPU model name from /proc/cpuinfo, with a portable fallback."""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or platform.machine()


def _read_total_ram_bytes() -> int | None:
    """Read total physical memory from /proc/meminfo when available."""
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    return None


def _environment_metadata() -> dict:
    """Collect software and hardware details needed to interpret a run."""
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_model": _read_cpu_model(),
        "cpu_count": os.cpu_count(),
        "total_ram_bytes": _read_total_ram_bytes(),
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "jsonschema_version": _package_version("jsonschema"),
        "tcd_version": _package_version("tcd"),
    }


def _build_metadata(
    run_id: str,
    *,
    model_name: str,
    tasks: list[Task],
    runs_per_task: int,
    max_tokens: int,
    temperature: float,
    max_retries: int,
    seed_base: int,
) -> dict:
    """Build the metadata document written next to the observations."""
    return {
        "run_id": run_id,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "model_name": model_name,
        "generation": {
            "runs_per_task": runs_per_task,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "max_retries": max_retries,
            "seed_base": seed_base,
            "seed_spacing": 100,
        },
        "tasks": [
            {
                "task_id": task.task_id,
                "description": task.description,
                "prompt": task.prompt,
                "schema": task.schema,
            }
            for task in tasks
        ],
        "environment": _environment_metadata(),
    }


# ---------------------------------------------------------------------------
# Strategy dispatch and error records
# ---------------------------------------------------------------------------

def _error_observation(
    approach: str,
    task: Task,
    run_index: int,
    seed: int,
    exc: Exception,
) -> dict:
    """Return a uniform record for a strategy call that raised.

    Measurements that were never produced are None rather than 0.0, because
    zero is a legitimate measured value and must not be confused with a
    missing measurement.
    """
    return {
        "approach": approach,
        "task_id": task.task_id,
        "run_index": run_index,
        "seed": seed,
        "output": "",
        "tokens_generated": None,
        "latency_s": None,
        "validation_time_s": None,
        "e2e_latency_s": None,
        "valid_json": False,
        "valid_schema": False,
        "finish_reason": None,
        "truncated": None,
        "retries": None,
        "exhausted_retries": None,
        "bind_time_s": None,
        "valid_token_ids_time_s": None,
        "consume_token_time_s": None,
        "error": f"{type(exc).__name__}: {exc}",
    }


def _run_strategy(
    approach: str,
    task: Task,
    decoder,
    *,
    run_index: int,
    seed: int,
    max_tokens: int,
    temperature: float,
    max_retries: int,
) -> dict:
    """Run one strategy, converting exceptions into error observations."""
    if approach not in APPROACHES:
        raise ValueError(f"unknown approach: {approach}")

    try:
        if approach == "normal":
            result = run_normal(
                task,
                decoder,
                run_index=run_index,
                seed=seed,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif approach == "retry":
            result = run_retry(
                task,
                decoder,
                run_index=run_index,
                seed=seed,
                max_retries=max_retries,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            result = run_constrained(
                task,
                decoder,
                run_index=run_index,
                seed=seed,
                max_tokens=max_tokens,
                temperature=temperature,
            )
    except Exception as exc:  # noqa: BLE001 - failures must be recorded, not lost
        return _error_observation(approach, task, run_index, seed, exc)

    result["error"] = None
    return result


# ---------------------------------------------------------------------------
# Warm-up and experiment execution
# ---------------------------------------------------------------------------

def _warm_up(
    decoder: Decoder,
    task: Task,
    *,
    max_tokens: int,
    temperature: float,
) -> None:
    """Prime both generation paths without recording any observation.

    The unconstrained call warms the model prefill. The constrained call also
    exercises bind(), valid_token_ids(), and consume_token(). TCD's per-call
    TokenIndex construction still happens in every real constrained run, so
    this warm-up does not hide that cost.
    """
    warmup_tokens = min(20, max_tokens)

    torch.manual_seed(SEED_BASE)
    decoder.generate(
        task.prompt,
        constraint=None,
        max_tokens=warmup_tokens,
        temperature=temperature,
    )

    torch.manual_seed(SEED_BASE)
    decoder.generate(
        task.prompt,
        constraint=JSONSchemaConstraint(task.schema),
        max_tokens=warmup_tokens,
        temperature=temperature,
    )


def _format_progress(record: dict, run_index: int, runs_per_task: int) -> str:
    """Format one short progress line for the terminal."""
    prefix = (
        f"[run {run_index + 1}/{runs_per_task}] "
        f"{record['task_id']} {record['approach']}"
    )
    if record["error"] is not None:
        return f"{prefix} | ERROR: {record['error']}"

    return (
        f"{prefix} | valid={record['valid_schema']} "
        f"tokens={record['tokens_generated']} "
        f"latency={record['latency_s']:.3f}s "
        f"e2e={record['e2e_latency_s']:.3f}s "
        f"retries={record['retries']} "
        f"finish={record['finish_reason']}"
    )


def _print_summary(counts: dict, runs_per_task: int, task_count: int) -> None:
    """Print a small validity summary. Raw results remain the source of truth."""
    total_per_approach = runs_per_task * task_count
    print("\nSummary")
    print("-------")
    for approach in APPROACHES:
        valid = counts[approach]["valid_schema"]
        retries = counts[approach]["retries"]
        print(
            f"{approach:12s} schema-valid {valid}/{total_per_approach} "
            f"(retries: {retries})"
        )


def run_experiment(
    decoder: Decoder,
    *,
    tasks: list[Task] | None = None,
    runs_per_task: int = RUNS_PER_TASK,
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
    max_retries: int = MAX_RETRIES,
    seed_base: int = SEED_BASE,
    model_name: str = MODEL_NAME,
    results_dir: Path = RESULTS_DIR,
) -> tuple[Path, Path]:
    """Run the full benchmark and return ``(metadata_path, observations_path)``.

    Parameters are explicit so the same code path can be used for a small
    pilot and for the full experiment.
    """
    if tasks is None:
        tasks = TASKS
    if not tasks:
        raise ValueError("tasks must not be empty")

    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    run_id = _make_run_id()
    metadata_path, observations_path = _result_paths(results_dir, run_id)
    metadata = _build_metadata(
        run_id,
        model_name=model_name,
        tasks=tasks,
        runs_per_task=runs_per_task,
        max_tokens=max_tokens,
        temperature=temperature,
        max_retries=max_retries,
        seed_base=seed_base,
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Run ID:       {run_id}")
    print(f"Model:        {model_name}")
    print(f"Metadata:     {metadata_path}")
    print(f"Observations: {observations_path}")
    print(
        f"Configuration: {runs_per_task} runs/task, max_tokens={max_tokens}, "
        f"temperature={temperature}, max_retries={max_retries}"
    )
    print("\nWarming up...")
    _warm_up(
        decoder,
        tasks[0],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    counts = {
        approach: {"valid_schema": 0, "retries": 0}
        for approach in APPROACHES
    }

    with observations_path.open("w", encoding="utf-8") as handle:
        for run_index in range(runs_per_task):
            seed = _seed_for_run(run_index, seed_base)
            for task in tasks:
                for approach in APPROACHES:
                    record = _run_strategy(
                        approach,
                        task,
                        decoder,
                        run_index=run_index,
                        seed=seed,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        max_retries=max_retries,
                    )
                    handle.write(json.dumps(record) + "\n")
                    handle.flush()

                    if record["valid_schema"]:
                        counts[approach]["valid_schema"] += 1
                    if record["retries"] is not None:
                        counts[approach]["retries"] += record["retries"]

                    print(
                        _format_progress(record, run_index, runs_per_task),
                        flush=True,
                    )

    _print_summary(counts, runs_per_task, len(tasks))
    return metadata_path, observations_path


def main() -> None:
    """Load the configured model and run the full experiment."""
    decoder = Decoder(MODEL_NAME)
    run_experiment(decoder)


if __name__ == "__main__":
    main()
