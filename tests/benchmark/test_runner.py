"""Tests for benchmark runner strategies."""

import time

import pytest

from benchmark.dataset import TASKS
from benchmark.runner import _validate, run_constrained, run_normal, run_retry
from tcd import JSONSchemaConstraint

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
    def __init__(self, output: str, tokens: int = 5, finish_reason: str = "eos"):
        self._output = output
        self._tokens = tokens
        self._finish_reason = finish_reason
        self.prompts = []

    def generate(
        self,
        prompt,
        constraint=None,
        max_tokens=100,
        temperature=0.8,
        _metrics=None,
    ):
        self.prompts.append(prompt)
        if _metrics is not None:
            _metrics["tokens_generated"] = self._tokens
            _metrics["finish_reason"] = self._finish_reason
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
    "tokens_generated", "latency_s", "validation_time_s", "e2e_latency_s",
    "valid_json", "valid_schema", "finish_reason", "truncated",
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


def test_run_normal_malformed_json_is_not_marked_truncated():
    # Malformed output that stopped for another reason is not truncation.
    decoder = FakeDecoder("not json", finish_reason="eos")
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["valid_json"] is False
    assert result["finish_reason"] == "eos"
    assert result["truncated"] is False


def test_run_normal_max_tokens_truncation_is_flagged():
    decoder = FakeDecoder('{"name": "Ada"', finish_reason="max_tokens")
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["valid_json"] is False
    assert result["finish_reason"] == "max_tokens"
    assert result["truncated"] is True


def test_run_normal_has_no_retries():
    decoder = FakeDecoder("not json")  # even on failure, no retry
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["retries"] == 0
    assert result["exhausted_retries"] is False


def test_run_normal_latency_is_positive():
    decoder = FakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["latency_s"] > 0


def test_run_normal_e2e_includes_generation_and_validation():
    decoder = FakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_normal(TC1, decoder, run_index=0, seed=42)
    assert result["validation_time_s"] >= 0.0
    assert result["e2e_latency_s"] >= (
        result["latency_s"] + result["validation_time_s"]
    )


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


def test_run_normal_uses_supplied_prompt():
    decoder = FakeDecoder('{"name": "Ada", "status": "ok"}')
    run_normal(TC1, decoder, prompt="CUSTOM", run_index=0, seed=42)
    assert decoder.prompts == ["CUSTOM"]


# ---------------------------------------------------------------------------
# Multi-output fake decoder for retry tests
#
# Returns outputs from a list in order. Each call consumes the next entry.
# If the list is exhausted, raises StopIteration — which would indicate a
# test that made more generate() calls than expected.
# ---------------------------------------------------------------------------

class MultiOutputFakeDecoder:
    def __init__(
        self,
        outputs: list[str],
        tokens_per_attempt: int = 5,
        finish_reasons: list[str] | None = None,
    ):
        self._outputs = iter(outputs)
        self._tokens = tokens_per_attempt
        self._finish_reasons = iter(finish_reasons or ["eos"] * len(outputs))
        self.prompts = []

    def generate(
        self,
        prompt,
        constraint=None,
        max_tokens=100,
        temperature=0.8,
        _metrics=None,
    ):
        self.prompts.append(prompt)
        if _metrics is not None:
            _metrics["tokens_generated"] = self._tokens
            _metrics["finish_reason"] = next(self._finish_reasons)
            _metrics["bind_time_s"] = 0.0
            _metrics["valid_token_ids_time_s"] = 0.0
            _metrics["consume_token_time_s"] = 0.0
        return next(self._outputs)


# Reuse the same REQUIRED_KEYS — all three strategies share the same schema.


# ---------------------------------------------------------------------------
# run_retry tests
# ---------------------------------------------------------------------------

def test_run_retry_succeeds_on_first_attempt_with_zero_retries():
    valid = '{"name": "Ada", "status": "ok"}'
    decoder = MultiOutputFakeDecoder([valid])
    result = run_retry(TC1, decoder, run_index=0, seed=42)
    assert result["valid_json"] is True
    assert result["valid_schema"] is True
    assert result["retries"] == 0
    assert result["exhausted_retries"] is False


def test_run_retry_retries_on_invalid_output_and_records_retry_count():
    invalid = "not json"
    valid = '{"name": "Ada", "status": "ok"}'
    decoder = MultiOutputFakeDecoder([invalid, valid])
    result = run_retry(TC1, decoder, run_index=0, seed=42)
    assert result["valid_json"] is True
    assert result["valid_schema"] is True
    assert result["retries"] == 1
    assert result["exhausted_retries"] is False


def test_run_retry_exhausts_retries_when_all_attempts_fail():
    decoder = MultiOutputFakeDecoder(["bad", "bad", "bad", "bad"])
    result = run_retry(TC1, decoder, run_index=0, seed=42, max_retries=3)
    assert result["retries"] == 3
    assert result["exhausted_retries"] is True
    assert result["valid_json"] is False


def test_run_retry_output_is_from_the_final_attempt():
    # The result should carry whichever output ended the loop — the
    # successful one if it existed, the last failure otherwise.
    invalid = "bad"
    valid = '{"name": "X", "status": "y"}'
    decoder = MultiOutputFakeDecoder([invalid, invalid, valid])
    result = run_retry(TC1, decoder, run_index=0, seed=42)
    assert result["output"] == valid


def test_run_retry_output_is_last_failure_when_all_exhausted():
    outputs = ["bad1", "bad2", "bad3", "bad4"]
    decoder = MultiOutputFakeDecoder(outputs)
    result = run_retry(TC1, decoder, run_index=0, seed=42, max_retries=3)
    assert result["output"] == "bad4"


def test_run_retry_tokens_generated_is_total_across_all_attempts():
    # Two attempts of 5 tokens each = 10 total.
    invalid = "not json"
    valid = '{"name": "Ada", "status": "ok"}'
    decoder = MultiOutputFakeDecoder([invalid, valid], tokens_per_attempt=5)
    result = run_retry(TC1, decoder, run_index=0, seed=42)
    assert result["tokens_generated"] == 10


def test_run_retry_tokens_generated_accumulates_across_all_failed_attempts():
    # Four failed attempts of 7 tokens each = 28 total.
    decoder = MultiOutputFakeDecoder(["bad"] * 4, tokens_per_attempt=7)
    result = run_retry(TC1, decoder, run_index=0, seed=42, max_retries=3)
    assert result["tokens_generated"] == 28


def test_run_retry_latency_is_positive():
    valid = '{"name": "Ada", "status": "ok"}'
    decoder = MultiOutputFakeDecoder([valid])
    result = run_retry(TC1, decoder, run_index=0, seed=42)
    assert result["latency_s"] > 0


def test_run_retry_validation_time_accumulates_across_attempts(monkeypatch):
    calls = []

    def slow_validate(output, schema):
        calls.append(output)
        time.sleep(0.005)
        return _validate(output, schema)

    monkeypatch.setattr("benchmark.runner._validate", slow_validate)

    invalid = "not json"
    valid = '{"name": "Ada", "status": "ok"}'
    decoder = MultiOutputFakeDecoder([invalid, valid])
    result = run_retry(TC1, decoder, run_index=0, seed=42)

    assert len(calls) == 2
    assert result["validation_time_s"] >= 0.01
    assert result["e2e_latency_s"] >= (
        result["latency_s"] + result["validation_time_s"]
    )


def test_run_retry_result_contains_all_required_keys():
    valid = '{"name": "Ada", "status": "ok"}'
    decoder = MultiOutputFakeDecoder([valid])
    result = run_retry(TC1, decoder, run_index=0, seed=42)
    assert REQUIRED_KEYS.issubset(result.keys())


def test_run_retry_approach_field_is_retry():
    valid = '{"name": "Ada", "status": "ok"}'
    decoder = MultiOutputFakeDecoder([valid])
    result = run_retry(TC1, decoder, run_index=0, seed=42)
    assert result["approach"] == "retry"


def test_run_retry_uses_supplied_prompt_for_every_attempt():
    decoder = MultiOutputFakeDecoder(
        ["not json", '{"name": "Ada", "status": "ok"}']
    )
    run_retry(TC1, decoder, prompt="CUSTOM", run_index=0, seed=42)
    assert decoder.prompts == ["CUSTOM", "CUSTOM"]


def test_run_retry_constraint_timings_are_always_zero():
    valid = '{"name": "Ada", "status": "ok"}'
    decoder = MultiOutputFakeDecoder([valid])
    result = run_retry(TC1, decoder, run_index=0, seed=42)
    assert result["bind_time_s"] == 0.0
    assert result["valid_token_ids_time_s"] == 0.0
    assert result["consume_token_time_s"] == 0.0


def test_run_retry_truncated_when_final_attempt_hits_max_tokens():
    decoder = MultiOutputFakeDecoder(
        ["bad"] * 4,
        finish_reasons=["max_tokens"] * 4,
    )
    result = run_retry(TC1, decoder, run_index=0, seed=42, max_retries=3)
    assert result["finish_reason"] == "max_tokens"
    assert result["truncated"] is True


def test_run_retry_truncation_reflects_the_final_attempt():
    invalid = "not json"
    valid = '{"name": "Ada", "status": "ok"}'
    decoder = MultiOutputFakeDecoder(
        [invalid, valid],
        finish_reasons=["max_tokens", "eos"],
    )
    result = run_retry(TC1, decoder, run_index=0, seed=42)
    assert result["finish_reason"] == "eos"
    assert result["truncated"] is False


def test_run_retry_valid_json_false_and_schema_false_when_exhausted():
    # When all attempts fail, both validity flags should reflect the
    # last failed output — not some earlier successful-looking partial state.
    decoder = MultiOutputFakeDecoder(["bad"] * 4)
    result = run_retry(TC1, decoder, run_index=0, seed=42, max_retries=3)
    assert result["valid_json"] is False
    assert result["valid_schema"] is False
    assert result["exhausted_retries"] is True


# ---------------------------------------------------------------------------
# Fake decoder for constrained tests
#
# Records the constraint argument it receives and reports configurable
# non-zero timing values so tests can verify the fields flow correctly
# from _metrics into the result dict.
# ---------------------------------------------------------------------------

class ConstrainedFakeDecoder:
    """Fake decoder that records received constraint and returns a fixed output."""

    def __init__(
        self,
        output: str,
        tokens: int = 8,
        bind_time: float = 0.1,
        valid_ids_time: float = 0.5,
        consume_time: float = 0.05,
        finish_reason: str = "constraint_complete",
    ):
        self._output = output
        self._tokens = tokens
        self._bind_time = bind_time
        self._valid_ids_time = valid_ids_time
        self._consume_time = consume_time
        self._finish_reason = finish_reason
        self.received_constraint = None
        self.prompts = []

    def generate(
        self,
        prompt,
        constraint=None,
        max_tokens=100,
        temperature=0.8,
        _metrics=None,
    ):
        self.received_constraint = constraint
        self.prompts.append(prompt)
        if _metrics is not None:
            _metrics["tokens_generated"] = self._tokens
            _metrics["finish_reason"] = self._finish_reason
            _metrics["bind_time_s"] = self._bind_time
            _metrics["valid_token_ids_time_s"] = self._valid_ids_time
            _metrics["consume_token_time_s"] = self._consume_time
        return self._output


# ---------------------------------------------------------------------------
# run_constrained tests
# ---------------------------------------------------------------------------

def test_run_constrained_result_contains_all_required_keys():
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_constrained(TC1, decoder, run_index=0, seed=42)
    assert REQUIRED_KEYS.issubset(result.keys())


def test_run_constrained_approach_field_is_constrained():
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_constrained(TC1, decoder, run_index=0, seed=42)
    assert result["approach"] == "constrained"


def test_run_constrained_passes_a_constraint_to_generate():
    # The fundamental difference from run_normal and run_retry: generate()
    # must receive a non-None constraint.
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "ok"}')
    run_constrained(TC1, decoder, run_index=0, seed=42)
    assert decoder.received_constraint is not None


def test_run_constrained_passes_a_json_schema_constraint():
    # Specifically a JSONSchemaConstraint, not an arbitrary object.
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "ok"}')
    run_constrained(TC1, decoder, run_index=0, seed=42)
    assert isinstance(decoder.received_constraint, JSONSchemaConstraint)


def test_run_constrained_valid_output_sets_both_flags_true():
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "active"}')
    result = run_constrained(TC1, decoder, run_index=0, seed=42)
    assert result["valid_json"] is True
    assert result["valid_schema"] is True
    assert result["finish_reason"] == "constraint_complete"
    assert result["truncated"] is False


def test_run_constrained_truncated_output_sets_both_flags_false():
    # Simulates hitting max_tokens before the constraint completes.
    decoder = ConstrainedFakeDecoder(
        '{"name": "Ada"',
        finish_reason="max_tokens",
    )
    result = run_constrained(TC1, decoder, run_index=0, seed=42)
    assert result["valid_json"] is False
    assert result["valid_schema"] is False
    assert result["finish_reason"] == "max_tokens"
    assert result["truncated"] is True


def test_run_constrained_has_no_retries():
    decoder = ConstrainedFakeDecoder("bad output")
    result = run_constrained(TC1, decoder, run_index=0, seed=42)
    assert result["retries"] == 0
    assert result["exhausted_retries"] is False


def test_run_constrained_latency_is_positive():
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_constrained(TC1, decoder, run_index=0, seed=42)
    assert result["latency_s"] > 0


def test_run_constrained_e2e_includes_generation_and_validation():
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_constrained(TC1, decoder, run_index=0, seed=42)
    assert result["validation_time_s"] >= 0.0
    assert result["e2e_latency_s"] >= (
        result["latency_s"] + result["validation_time_s"]
    )


def test_run_constrained_tokens_generated_matches_decoder_report():
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "ok"}', tokens=14)
    result = run_constrained(TC1, decoder, run_index=0, seed=42)
    assert result["tokens_generated"] == 14


def test_run_constrained_timing_fields_propagate_from_metrics():
    # Non-zero timing values reported by the decoder must appear unchanged
    # in the result. This confirms the fields are read from _metrics rather
    # than hardcoded.
    decoder = ConstrainedFakeDecoder(
        '{"name": "Ada", "status": "ok"}',
        bind_time=0.12,
        valid_ids_time=0.63,
        consume_time=0.07,
    )
    result = run_constrained(TC1, decoder, run_index=0, seed=42)
    assert result["bind_time_s"] == pytest.approx(0.12)
    assert result["valid_token_ids_time_s"] == pytest.approx(0.63)
    assert result["consume_token_time_s"] == pytest.approx(0.07)


def test_run_constrained_records_run_index_and_seed():
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "ok"}')
    result = run_constrained(TC1, decoder, run_index=2, seed=77)
    assert result["run_index"] == 2
    assert result["seed"] == 77


def test_run_constrained_uses_supplied_prompt():
    decoder = ConstrainedFakeDecoder('{"name": "Ada", "status": "ok"}')
    run_constrained(TC1, decoder, prompt="CUSTOM", run_index=0, seed=42)
    assert decoder.prompts == ["CUSTOM"]
