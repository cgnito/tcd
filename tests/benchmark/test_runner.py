"""Tests for benchmark runner strategies."""

import pytest

from benchmark.dataset import TASKS
from benchmark.runner import _validate, run_normal


# ---------------------------------------------------------------------------
# Shared fixture: a simple task with a known schema
# ---------------------------------------------------------------------------

# TC-1 is the simplest schema: {"name": str, "status": str}.
# Using a fixed task from the dataset keeps tests aligned with real benchmark
# inputs rather than inventing a separate schema just for testing.
TC1 = next(t for t in TASKS if t.task_id == "TC-1")


# ---------------------------------------------------------------------------
# Fake decoder
#
# Returns a controllable output string without loading a model.
# Populates _metrics the same way decoder.generate() does so the runner
# code that reads _metrics["tokens_generated"] etc. works correctly.
# ---------------------------------------------------------------------------

class FakeDecoder:
    def __init__(self, output: str, tokens: int = 5):
        self._output = output
        self._tokens = tokens

    def generate(
        self,
        prompt,
        constraint=None,
        max_tokens=100,
        temperature=0.8,
        _metrics=None,
    ):
        if _metrics is not None:
            _metrics["tokens_generated"] = self._tokens
            _metrics["bind_time_s"] = 0.0
            _metrics["valid_token_ids_time_s"] = 0.0
            _metrics["consume_token_time_s"] = 0.0
        return self._output


# ---------------------------------------------------------------------------
# _validate tests
# ---------------------------------------------------------------------------

def test_validate_returns_true_true_for_valid_json_and_schema():
    output = '{"name": "Ada", "status": "active"}'
    valid_json, valid_schema = _validate(output, TC1.schema)
    assert valid_json is True
    assert valid_schema is True


def test_validate_returns_true_false_for_valid_json_failing_schema():
    # Missing required field "status".
    output = '{"name": "Ada"}'
    valid_json, valid_schema = _validate(output, TC1.schema)
    assert valid_json is True
    assert valid_schema is False


def test_validate_returns_false_false_for_invalid_json():
    output = "this is not json at all"
    valid_json, valid_schema = _validate(output, TC1.schema)
    assert valid_json is False
    assert valid_schema is False


def test_validate_returns_false_false_for_truncated_json():
    # A common unconstrained failure mode: generation cut off mid-object.
    output = '{"name": "Ada", "status":'
    valid_json, valid_schema = _validate(output, TC1.schema)
    assert valid_json is False
    assert valid_schema is False


def test_validate_schema_invalid_is_not_false_false():
    # Confirm valid_json is True even when schema fails — the two flags are
    # independent. If both were always the same value, the distinction would
    # be meaningless.
    output = '{"name": "Ada", "unexpected_field": true}'
    # TC-1 has additionalProperties: false, so this should fail schema.
    valid_json, valid_schema = _validate(output, TC1.schema)
    assert valid_json is True
    assert valid_schema is False


# ---------------------------------------------------------------------------
# run_normal tests
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "approach", "task_id", "run_index", "seed", "output",
    "tokens_generated", "latency_s", "valid_json", "valid_schema",
    "retries", "exhausted_retries",
    "bind_time_s", "valid_token_ids_time_s", "consume_token_time_s",
}


def test_run_normal_result_contains_all_required_keys():
    decoder = FakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert REQUIRED_KEYS.issubset(result.keys())


def test_run_normal_records_correct_approach_and_task_id():
    decoder = FakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["approach"] == "normal"
    assert result["task_id"] == "TC-1"


def test_run_normal_records_run_index_and_seed():
    decoder = FakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_normal(TC1, decoder, run_index=3, seed=99)
    assert result["run_index"] == 3
    assert result["seed"] == 99


def test_run_normal_valid_output_sets_both_flags_true():
    decoder = FakeDecoder('{"name": "Ada", "status": "active"}')
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["valid_json"] is True
    assert result["valid_schema"] is True


def test_run_normal_schema_invalid_output_sets_valid_json_true_schema_false():
    decoder = FakeDecoder('{"name": "Ada"}')  # missing "status"
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["valid_json"] is True
    assert result["valid_schema"] is False


def test_run_normal_broken_json_sets_both_flags_false():
    decoder = FakeDecoder("not json")
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["valid_json"] is False
    assert result["valid_schema"] is False


def test_run_normal_has_no_retries():
    decoder = FakeDecoder("not json")  # even on failure, no retry
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["retries"] == 0
    assert result["exhausted_retries"] is False


def test_run_normal_latency_is_positive():
    decoder = FakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["latency_s"] > 0


def test_run_normal_tokens_generated_matches_decoder_report():
    decoder = FakeDecoder('{"name": "Ada", "status": "ok"}', tokens=12)
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["tokens_generated"] == 12


def test_run_normal_constraint_timings_are_zero():
    # Approach A is unconstrained. All three constraint timing fields must
    # be exactly 0.0, not merely small.
    decoder = FakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["bind_time_s"] == 0.0
    assert result["valid_token_ids_time_s"] == 0.0
    assert result["consume_token_time_s"] == 0.0


def test_run_normal_output_field_contains_raw_generation():
    raw = '{"name": "Ada", "status": "ok"}'
    decoder = FakeDecoder(raw)
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["output"] == raw
