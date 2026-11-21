"""Tests for benchmark aggregation."""

import json
from pathlib import Path

from benchmark.analyze import (
    _failure_modes,
    _fence_sensitivity,
    _format_report,
    _infer_metadata_path,
    _latest_observations,
    _load_records,
    _load_schemas,
    _strip_code_fence,
    _summarize_overall,
    main,
)
from benchmark.dataset import TASKS

TC1 = next(t for t in TASKS if t.task_id == "TC-1")


def _record(
    *,
    approach="normal",
    task_id="TC-1",
    valid_json=True,
    valid_schema=True,
    output='{"name": "Ada", "status": "ok"}',
    latency_s=1.0,
    tokens_generated=10,
    truncated=False,
    retries=0,
    error=None,
):
    return {
        "approach": approach,
        "task_id": task_id,
        "valid_json": valid_json,
        "valid_schema": valid_schema,
        "output": output,
        "latency_s": latency_s,
        "tokens_generated": tokens_generated,
        "truncated": truncated,
        "retries": retries,
        "error": error,
    }


def test_latest_observations_uses_latest_filename(tmp_path):
    older = tmp_path / "20260101T000000000000Z_observations.jsonl"
    newer = tmp_path / "20260102T000000000000Z_observations.jsonl"
    older.write_text("", encoding="utf-8")
    newer.write_text("", encoding="utf-8")

    assert _latest_observations(tmp_path) == newer


def test_latest_observations_falls_back_to_published(tmp_path):
    published = tmp_path / "published"
    published.mkdir()
    result = published / "20260101T000000000000Z_observations.jsonl"
    result.write_text("", encoding="utf-8")

    assert _latest_observations(tmp_path) == result


def test_infer_metadata_path_returns_existing_sibling(tmp_path):
    observations = tmp_path / "run_observations.jsonl"
    metadata = tmp_path / "run_metadata.json"
    observations.write_text("", encoding="utf-8")
    metadata.write_text("{}", encoding="utf-8")

    assert _infer_metadata_path(observations) == metadata


def test_load_records_skips_blank_lines(tmp_path):
    path = tmp_path / "observations.jsonl"
    path.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")

    assert _load_records(path) == [{"a": 1}, {"b": 2}]


def test_load_records_reports_malformed_line(tmp_path):
    path = tmp_path / "observations.jsonl"
    path.write_text("{bad}\n", encoding="utf-8")

    try:
        _load_records(path)
    except ValueError as exc:
        assert ":1:" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_load_schemas_reads_task_schemas(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(
        json.dumps({"tasks": [{"task_id": "TC-1", "schema": TC1.schema}]}),
        encoding="utf-8",
    )

    assert _load_schemas(path) == {"TC-1": TC1.schema}


def test_strip_code_fence_handles_json_and_plain_fences():
    assert _strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_code_fence("[1]\n```") is None
    assert _strip_code_fence("```\n[1]\n```") == "[1]"


def test_strip_code_fence_returns_none_for_unfenced_output():
    assert _strip_code_fence('{"a": 1}') is None


def test_summarize_counts_averages_and_ignores_missing_measurements():
    records = [
        _record(latency_s=1.0, tokens_generated=10),
        _record(
            valid_json=False,
            valid_schema=False,
            latency_s=3.0,
            tokens_generated=20,
            truncated=True,
        ),
        _record(
            approach="retry",
            valid_schema=False,
            latency_s=2.0,
            tokens_generated=5,
            retries=1,
        ),
        _record(
            approach="constrained",
            latency_s=None,
            tokens_generated=None,
            error="RuntimeError: boom",
        ),
    ]

    summary = _summarize_overall(records)

    assert summary["normal"]["n"] == 2
    assert summary["normal"]["valid_schema"] == 1
    assert summary["normal"]["valid_json"] == 1
    assert summary["normal"]["truncated"] == 1
    assert summary["normal"]["mean_latency_s"] == 2.0
    assert summary["normal"]["mean_tokens"] == 15.0
    assert summary["normal"]["tokens_per_s"] == 7.5
    assert summary["retry"]["retries"] == 1
    assert summary["constrained"]["errors"] == 1
    assert summary["constrained"]["mean_latency_s"] is None


def test_failure_modes_separate_invalid_json_schema_and_errors():
    records = [
        _record(
            valid_json=False,
            valid_schema=False,
            output="not json",
        ),
        _record(
            valid_json=True,
            valid_schema=False,
            output='{"name": "Ada"}',
        ),
        _record(
            valid_json=False,
            valid_schema=False,
            error="RuntimeError: boom",
        ),
    ]

    counts = _failure_modes(records)["normal"]

    assert counts["invalid_json"] == 1
    assert counts["schema_invalid"] == 1
    assert counts["errors"] == 1


def test_fence_sensitivity_recovers_valid_fenced_json():
    records = [
        _record(
            valid_json=False,
            valid_schema=False,
            output='```json\n{"name": "Ada", "status": "ok"}\n```',
        )
    ]

    sensitivity = _fence_sensitivity(records, {"TC-1": TC1.schema})["normal"]

    assert sensitivity["fenced_invalid"] == 1
    assert sensitivity["recovered"] == 1
    assert sensitivity["lenient_valid"] == 1


def test_fence_sensitivity_does_not_recover_schema_invalid_json():
    records = [
        _record(
            valid_json=False,
            valid_schema=False,
            output='```json\n{"name": "Ada"}\n```',
        )
    ]

    sensitivity = _fence_sensitivity(records, {"TC-1": TC1.schema})["normal"]

    assert sensitivity["recovered"] == 0
    assert sensitivity["still_schema_invalid"] == 1
    assert sensitivity["lenient_valid"] == 0


def test_format_report_contains_all_sections():
    report = _format_report(
        [_record()],
        observations_path=Path("obs.jsonl"),
        metadata_path=Path("meta.json"),
        schemas={"TC-1": TC1.schema},
    )

    assert "Overall" in report
    assert "Per task" in report
    assert "Primary failure modes" in report
    assert "Fence-stripped sensitivity" in report
    assert "lenient_valid=" in report


def test_main_prints_report_for_explicit_observations(tmp_path, capsys):
    observations = tmp_path / "run_observations.jsonl"
    metadata = tmp_path / "run_metadata.json"
    observations.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    metadata.write_text(
        json.dumps({"tasks": [{"task_id": "TC-1", "schema": TC1.schema}]}),
        encoding="utf-8",
    )

    assert main([str(observations)]) == 0
    assert "Overall" in capsys.readouterr().out
