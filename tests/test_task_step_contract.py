from __future__ import annotations

import pytest

from lca.contracts.harness.tasks.task import StepStatus, TaskStep


def test_task_step_tracks_attempt_and_artifact_refs() -> None:
    step = TaskStep(
        task_id="task-1",
        step_id="step-1",
        node_ref="think.main",
        status=StepStatus.RUNNING,
        attempt=2,
        input_ref="artifact:input",
    )

    assert step.status is StepStatus.RUNNING
    assert step.attempt == 2
    assert step.input_ref == "artifact:input"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"task_id": "", "step_id": "step-1", "node_ref": "act.main"},
        {"task_id": "task-1", "step_id": "step-1", "node_ref": "act.main", "attempt": -1},
        {
            "task_id": "task-1",
            "step_id": "step-1",
            "node_ref": "act.main",
            "status": StepStatus.SUCCEEDED,
            "error_code": "TOOL_FAILED",
        },
    ],
)
def test_task_step_rejects_invalid_snapshot(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        TaskStep(**kwargs)
