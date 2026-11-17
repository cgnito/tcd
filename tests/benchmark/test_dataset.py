"""Sanity checks for the benchmark task definitions.

These tests run before any generation happens. They confirm that the dataset
itself is internally consistent and that every schema is within TCD's
supported subset. A schema error caught here is far cheaper than one
discovered mid-benchmark.
"""

import pytest

from benchmark.dataset import TASKS, Task
from tcd.json_parser.schema import SchemaError, compile_schema


def test_dataset_is_nonempty():
    assert len(TASKS) > 0


def test_all_tasks_are_task_instances():
    assert all(isinstance(t, Task) for t in TASKS)


def test_task_ids_are_unique():
    ids = [task.task_id for task in TASKS]
    assert len(ids) == len(set(ids)), "duplicate task_id found in TASKS"


@pytest.mark.parametrize("task", TASKS, ids=[t.task_id for t in TASKS])
def test_task_has_nonempty_prompt(task):
    assert task.prompt.strip(), f"{task.task_id}: prompt must not be empty"


@pytest.mark.parametrize("task", TASKS, ids=[t.task_id for t in TASKS])
def test_task_has_nonempty_description(task):
    assert task.description.strip(), f"{task.task_id}: description must not be empty"


@pytest.mark.parametrize("task", TASKS, ids=[t.task_id for t in TASKS])
def test_task_schema_is_within_tcd_supported_subset(task):
    """Confirm each schema compiles without raising SchemaError.

    compile_schema is the same function used by JSONSchemaConstraint
    internally. If a schema uses an unsupported keyword, this test
    catches it here rather than at benchmark runtime.
    """
    try:
        compile_schema(task.schema)
    except SchemaError as exc:
        pytest.fail(f"{task.task_id}: schema is outside TCD's supported subset: {exc}")
