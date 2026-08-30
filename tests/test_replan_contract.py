from __future__ import annotations

import pytest

from lca.contracts.harness.think.replan import ReplanAction, ReplanRequest


def test_replan_request_allows_bounded_tool_replacement() -> None:
    request = ReplanRequest(
        task_id="task-1",
        failed_step_id="step-2",
        action=ReplanAction.REPLACE,
        reason="primary search timed out",
        replacement="search.cached",
        affected_step_ids=("step-2", "step-3"),
    )

    assert request.action is ReplanAction.REPLACE
    assert request.replacement == "search.cached"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"task_id": "", "failed_step_id": "step", "action": ReplanAction.RETRY, "reason": "x"},
        {
            "task_id": "task",
            "failed_step_id": "step",
            "action": ReplanAction.REPLACE,
            "reason": "x",
        },
        {
            "task_id": "task",
            "failed_step_id": "step",
            "action": ReplanAction.RETRY,
            "reason": "x",
            "replacement": "tool",
        },
    ],
)
def test_replan_request_rejects_unsafe_shape(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ReplanRequest(**kwargs)


def test_replan_scope_rejects_completed_step_mutation() -> None:
    from lca.contracts.harness.think.replan import validate_replan_scope

    request = ReplanRequest(
        task_id="task-1",
        failed_step_id="step-2",
        action=ReplanAction.REPLACE,
        reason="fallback",
        replacement="search.cached",
        affected_step_ids=("step-2", "step-3"),
    )

    with pytest.raises(ValueError, match="step-3"):
        validate_replan_scope(request, completed_step_ids=frozenset({"step-3"}))


def test_replan_scope_allows_pending_step_mutation() -> None:
    from lca.contracts.harness.think.replan import validate_replan_scope

    request = ReplanRequest(
        task_id="task-1",
        failed_step_id="step-2",
        action=ReplanAction.RETRY,
        reason="transient timeout",
        affected_step_ids=("step-2",),
    )

    validate_replan_scope(request, completed_step_ids=frozenset({"step-1"}))
