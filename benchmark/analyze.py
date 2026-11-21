"""Aggregate benchmark observations into summary tables.

Canonical invocation (from the project root)::

    uv run python -m benchmark.analyze

With no path, the most recent ``*_observations.jsonl`` file in
``benchmark/results/`` is analyzed. A specific observations file can also be
passed explicitly.

The primary summary uses the ``valid_json`` and ``valid_schema`` flags recorded
by the benchmark runner. The fence-stripped sensitivity section is post-hoc
only: it never changes the primary measurements.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path
from typing import Any

import jsonschema

APPROACHES = ("normal", "retry", "constrained")
RESULTS_DIR = Path(__file__).resolve().parent / "results"

_FENCED_OUTPUT = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def _latest_observations(results_dir: Path = RESULTS_DIR) -> Path:
    """Return the most recent observations file by run-id filename.

    New runs are written directly under ``results/``. If none exist, fall back
    to the tracked published run so the analyzer works from a fresh clone.
    """
    results_dir = Path(results_dir)
    paths = sorted(results_dir.glob("*_observations.jsonl"))
    if not paths:
        paths = sorted((results_dir / "published").glob("*_observations.jsonl"))
    if not paths:
        raise FileNotFoundError(f"no observations found in {results_dir}")
    return paths[-1]


def _infer_metadata_path(observations_path: Path) -> Path | None:
    """Infer the metadata path that sits next to an observations file."""
    suffix = "_observations.jsonl"
    if not observations_path.name.endswith(suffix):
        return None
    candidate = observations_path.with_name(
        observations_path.name[: -len(suffix)] + "_metadata.json"
    )
    return candidate if candidate.exists() else None


def _load_records(observations_path: Path) -> list[dict[str, Any]]:
    """Load JSONL observations, reporting the line number on malformed input."""
    records = []
    for line_number, line in enumerate(
        Path(observations_path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{observations_path}:{line_number}: invalid JSON: {exc}"
            ) from exc
    return records


def _load_schemas(metadata_path: Path | None) -> dict[str, dict]:
    """Return task schemas keyed by task_id from a metadata document."""
    if metadata_path is None or not Path(metadata_path).exists():
        return {}
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    return {
        task["task_id"]: task["schema"]
        for task in metadata.get("tasks", [])
        if "task_id" in task and "schema" in task
    }


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize one approach, ignoring missing measurements from errors."""
    latencies = [
        record["latency_s"]
        for record in records
        if record.get("latency_s") is not None
    ]
    tokens = [
        record["tokens_generated"]
        for record in records
        if record.get("tokens_generated") is not None
    ]
    total_tokens = sum(tokens)
    total_latency = sum(latencies)

    return {
        "n": len(records),
        "valid_schema": sum(bool(record.get("valid_schema")) for record in records),
        "valid_json": sum(bool(record.get("valid_json")) for record in records),
        "truncated": sum(bool(record.get("truncated")) for record in records),
        "retries": sum(record.get("retries") or 0 for record in records),
        "errors": sum(record.get("error") is not None for record in records),
        "mean_latency_s": _mean(latencies),
        "median_latency_s": _median(latencies),
        "mean_tokens": _mean(tokens),
        "total_tokens": total_tokens,
        "tokens_per_s": (
            total_tokens / total_latency if total_latency > 0 else None
        ),
    }


def _summarize_overall(records: list[dict[str, Any]]) -> dict[str, dict]:
    return {
        approach: _summarize(
            [
                record
                for record in records
                if record.get("approach") == approach
            ]
        )
        for approach in APPROACHES
    }


def _summarize_by_task(records: list[dict[str, Any]]) -> dict[str, dict]:
    task_ids = sorted({record.get("task_id") for record in records})
    return {
        task_id: {
            approach: _summarize(
                [
                    record
                    for record in records
                    if record.get("task_id") == task_id
                    and record.get("approach") == approach
                ]
            )
            for approach in APPROACHES
        }
        for task_id in task_ids
    }


def _strip_code_fence(output: str) -> str | None:
    """Return the contents of a Markdown code fence, or None if not fenced."""
    match = _FENCED_OUTPUT.match(output)
    return match.group(1) if match else None


def _failure_modes(records: list[dict[str, Any]]) -> dict[str, dict]:
    """Count primary failure categories without changing recorded results."""
    result = {}
    for approach in APPROACHES:
        selected = [
            record
            for record in records
            if record.get("approach") == approach
        ]
        result[approach] = {
            "errors": sum(
                record.get("error") is not None for record in selected
            ),
            "invalid_json": sum(
                record.get("error") is None
                and not record.get("valid_json")
                for record in selected
            ),
            "schema_invalid": sum(
                record.get("error") is None
                and bool(record.get("valid_json"))
                and not record.get("valid_schema")
                for record in selected
            ),
            "fenced": sum(
                not record.get("valid_schema")
                and _strip_code_fence(record.get("output", "")) is not None
                for record in selected
            ),
        }
    return result


def _fence_sensitivity(
    records: list[dict[str, Any]],
    schemas: dict[str, dict],
) -> dict[str, dict]:
    """Report how many fenced failures would pass after fence stripping."""
    result = {}
    for approach in APPROACHES:
        selected = [
            record
            for record in records
            if record.get("approach") == approach
            and not record.get("valid_schema")
        ]
        fenced = [
            record
            for record in selected
            if _strip_code_fence(record.get("output", "")) is not None
        ]

        recovered = 0
        still_invalid_json = 0
        still_schema_invalid = 0
        missing_schema = 0

        for record in fenced:
            schema = schemas.get(record.get("task_id"))
            if schema is None:
                missing_schema += 1
                continue
            inner = _strip_code_fence(record.get("output", ""))
            try:
                parsed = json.loads(inner)
            except (json.JSONDecodeError, TypeError, ValueError):
                still_invalid_json += 1
                continue
            try:
                jsonschema.validate(instance=parsed, schema=schema)
            except jsonschema.ValidationError:
                still_schema_invalid += 1
            else:
                recovered += 1

        primary_valid = sum(
            bool(record.get("valid_schema"))
            for record in records
            if record.get("approach") == approach
        )
        result[approach] = {
            "fenced_invalid": len(fenced),
            "recovered": recovered,
            "still_invalid_json": still_invalid_json,
            "still_schema_invalid": still_schema_invalid,
            "missing_schema": missing_schema,
            "primary_valid": primary_valid,
            "lenient_valid": primary_valid + recovered,
            "n": sum(
                record.get("approach") == approach for record in records
            ),
        }
    return result


def _format_rate(count: int, total: int) -> str:
    percentage = 100.0 * count / total if total else 0.0
    return f"{count}/{total} ({percentage:.0f}%)"


def _format_number(value: float | None, digits: int = 2, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{suffix}"


def _format_report(
    records: list[dict[str, Any]],
    *,
    observations_path: Path,
    metadata_path: Path | None,
    schemas: dict[str, dict],
) -> str:
    overall = _summarize_overall(records)
    by_task = _summarize_by_task(records)
    failures = _failure_modes(records)
    sensitivity = _fence_sensitivity(records, schemas)

    lines = [
        f"Observations: {observations_path}",
        f"Metadata:     {metadata_path if metadata_path else 'not found'}",
        f"Records:      {len(records)}",
        "",
        "Overall",
        "-------",
        (
            f"{'approach':<12} {'valid schema':>18} {'valid JSON':>18} "
            f"{'trunc':>6} {'retries':>8} {'mean lat':>10} "
            f"{'med lat':>9} {'mean tok':>9} {'tok/s':>8}"
        ),
    ]

    for approach in APPROACHES:
        summary = overall[approach]
        lines.append(
            f"{approach:<12} "
            f"{_format_rate(summary['valid_schema'], summary['n']):>18} "
            f"{_format_rate(summary['valid_json'], summary['n']):>18} "
            f"{summary['truncated']:>6} {summary['retries']:>8} "
            f"{_format_number(summary['mean_latency_s'], 2, 's'):>10} "
            f"{_format_number(summary['median_latency_s'], 2, 's'):>9} "
            f"{_format_number(summary['mean_tokens'], 1):>9} "
            f"{_format_number(summary['tokens_per_s'], 2):>8}"
        )

    lines.extend(
        [
            "",
            "Per task",
            "--------",
            (
                f"{'task':<6} {'approach':<12} {'valid':>10} "
                f"{'mean lat':>10} {'mean tok':>9} {'trunc':>6}"
            ),
        ]
    )

    for task_id, approaches in by_task.items():
        for approach in APPROACHES:
            summary = approaches[approach]
            lines.append(
                f"{task_id:<6} {approach:<12} "
                f"{_format_rate(summary['valid_schema'], summary['n']):>10} "
                f"{_format_number(summary['mean_latency_s'], 2, 's'):>10} "
                f"{_format_number(summary['mean_tokens'], 1):>9} "
                f"{summary['truncated']:>6}"
            )

    lines.extend(
        [
            "",
            "Primary failure modes",
            "---------------------",
        ]
    )
    for approach in APPROACHES:
        counts = failures[approach]
        lines.append(
            f"{approach:<12} "
            f"invalid_json={counts['invalid_json']} "
            f"schema_invalid={counts['schema_invalid']} "
            f"errors={counts['errors']} "
            f"fenced={counts['fenced']}"
        )

    lines.extend(
        [
            "",
            "Fence-stripped sensitivity (post-hoc only)",
            "------------------------------------------",
        ]
    )
    if metadata_path is None:
        lines.append("metadata not found; sensitivity validation skipped")
    else:
        for approach in APPROACHES:
            counts = sensitivity[approach]
            lines.append(
                f"{approach:<12} "
                f"fenced_invalid={counts['fenced_invalid']} "
                f"recovered={counts['recovered']} "
                f"still_invalid_json={counts['still_invalid_json']} "
                f"still_schema_invalid={counts['still_schema_invalid']} "
                f"missing_schema={counts['missing_schema']} "
                f"lenient_valid="
                f"{_format_rate(counts['lenient_valid'], counts['n'])}"
            )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize TCD benchmark observations.",
    )
    parser.add_argument(
        "observations",
        nargs="?",
        type=Path,
        help="observations JSONL path; defaults to the latest result",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="metadata JSON path; inferred from the observations filename",
    )
    args = parser.parse_args(argv)

    observations_path = args.observations or _latest_observations()
    records = _load_records(observations_path)
    metadata_path = (
        args.metadata
        if args.metadata is not None
        else _infer_metadata_path(observations_path)
    )
    schemas = _load_schemas(metadata_path)
    print(
        _format_report(
            records,
            observations_path=observations_path,
            metadata_path=metadata_path,
            schemas=schemas,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
