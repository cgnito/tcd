"""Tests for the benchmark entry point."""

import json
from pathlib import Path

from benchmark.dataset import TASKS
from benchmark.run_benchmark import (
    _build_metadata,
    _result_paths,
    _run_strategy,
    _seed_for_run,
    run_experiment,
)

TC1 = next(t for t in TASKS if t.task_id == "TC-1")


class FakeDecoder:
    def generate(
        self,
        prompt,
        constraint=None,
        max_tokens=100,
        temperature=0.8,
        _metrics=None,
    ):
        if _metrics is not None:
            _metrics["tokens_generated"] = 3
            _metrics["finish_reason"] = (
                "constraint_complete" if constraint is not None else "eos"
            )
            _metrics["bind_time_s"] = 0.0
            _metrics["valid_token_ids_time_s"] = 0.0
            _metrics["consume_token_time_s"] = 0.0
        return '{"name": "Ada", "status": "ok"}'


class BrokenDecoder:
    def generate(self, *args, **kwargs):
        raise RuntimeError("boom")


def test_seed_spacing_leaves_room_for_retries():
    assert _seed_for_run(0) == 0
    assert _seed_for_run(1) == 100
    assert _seed_for_run(2) == 200
    assert _seed_for_run(2, seed_base=7) == 207


def test_result_paths_use_run_id():
    metadata_path, observations_path = _result_paths(Path("/tmp"), "abc")
    assert metadata_path == Path("/tmp/abc_metadata.json")
    assert observations_path == Path("/tmp/abc_observations.jsonl")


def test_metadata_contains_configuration_and_environment():
    metadata = _build_metadata(
        "run-1",
        model_name="fake-model",
        tasks=[TC1],
        runs_per_task=2,
        max_tokens=10,
        temperature=0.5,
        max_retries=1,
        seed_base=7,
    )

    assert metadata["run_id"] == "run-1"
    assert metadata["model_name"] == "fake-model"
    assert metadata["generation"] == {
        "runs_per_task": 2,
        "max_tokens": 10,
        "temperature": 0.5,
        "max_retries": 1,
        "seed_base": 7,
        "seed_spacing": 100,
    }
    assert metadata["tasks"][0]["task_id"] == "TC-1"
    assert metadata["tasks"][0]["schema"] == TC1.schema
    assert "environment" in metadata


def test_run_strategy_adds_error_none_on_success():
    record = _run_strategy(
        "normal",
        TC1,
        FakeDecoder(),
        run_index=0,
        seed=0,
        max_tokens=10,
        temperature=0.5,
        max_retries=1,
    )

    assert record["approach"] == "normal"
    assert record["error"] is None
    assert record["valid_schema"] is True


def test_run_strategy_converts_exception_to_error_record():
    record = _run_strategy(
        "normal",
        TC1,
        BrokenDecoder(),
        run_index=0,
        seed=0,
        max_tokens=10,
        temperature=0.5,
        max_retries=1,
    )

    assert record["approach"] == "normal"
    assert record["task_id"] == "TC-1"
    assert record["error"] == "RuntimeError: boom"
    assert record["tokens_generated"] is None
    assert record["latency_s"] is None
    assert record["validation_time_s"] is None
    assert record["e2e_latency_s"] is None
    assert record["finish_reason"] is None
    assert record["truncated"] is None
    assert record["retries"] is None
    assert record["valid_json"] is False
    assert record["valid_schema"] is False


def test_run_experiment_writes_metadata_and_jsonl(tmp_path):
    metadata_path, observations_path = run_experiment(
        FakeDecoder(),
        tasks=[TC1],
        runs_per_task=2,
        results_dir=tmp_path,
        model_name="fake-model",
    )

    assert metadata_path.exists()
    assert observations_path.exists()

    lines = observations_path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]

    assert len(records) == 2 * 1 * 3
    assert {record["approach"] for record in records} == {
        "normal",
        "retry",
        "constrained",
    }
    assert {record["run_index"] for record in records} == {0, 1}
    assert {record["seed"] for record in records} == {0, 100}
    assert all(record["task_id"] == "TC-1" for record in records)
    assert all(record["error"] is None for record in records)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["model_name"] == "fake-model"
    assert metadata["generation"]["runs_per_task"] == 2
