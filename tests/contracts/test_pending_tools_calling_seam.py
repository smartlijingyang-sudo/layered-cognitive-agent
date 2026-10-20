"""RA-171: the fresh-pause and restart-recovery paths must derive identical
pending_tools_calling lists from the same approval_request.

Three drifts existed before the convergence:
1. fresh skipped empty tool_name/call_id entries, recovery kept them;
2. fresh injected lca_run_id into askUserQuestion arguments, recovery
   dropped it (frontend submit could not resume a recovered run);
3. fresh recorded step.tool_call.record pending_approval facts, recovery
   skipped them (this one is intentional per ADR-0195 P4-S04 — the recovery
   journal stays minimal and reuses the pause-time journal.json).

The convergence puts the derivation behind one seam
(pending_tools_calling_from); these tests fail on the pre-fix code and
pass after, with no reference to the new seam itself.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import patch

from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import Budget

_APPROVAL_REQUEST: dict[str, Any] = {
    "approval_id": "plan:intervene.interrupt:1",
    "type": "ask_user_question",
    "tool_calls": [
        {
            "call_id": "toolu_1",
            "tool_name": "askUserQuestion",
            "arguments": {"questions": [{"question": "name"}]},
        },
        {
            "call_id": "toolu_2",
            "tool_name": "runBash",
            "arguments": {"cmd": "ls"},
        },
        # Identity-less entry: the fresh path skips it, old recovery kept it.
        {"call_id": "", "tool_name": "", "arguments": {}},
        "not-a-dict",
    ],
}


class _FakeScope:
    run_id = "run_test"


def _pending_via_fresh_pause(
    approval_request: dict[str, Any],
) -> list[dict[str, Any]]:
    checkpoint_kwargs: list[dict] = []
    result = Result(
        trace_id="trace_1",
        status=TaskStatus.INPUT_REQUIRED,
        final_state_ref="mem://trace_1/0",
        total_steps=1,
        budget_used=Budget(),
        extra={
            "approval_request": approval_request,
            "state_snapshot": {"snapshot_id": "snap_1"},
        },
    )
    with (
        patch(
            "lca.infrastructure.observability.facade.run.context.get_current_run_scope",
            return_value=_FakeScope(),
        ),
        patch(
            "lca.infrastructure.tools.run.finalizer.get_current_run_id",
            return_value=None,
        ),
        patch(
            "lca.loop.commit.tool_journal.record_step_tool_call",
            side_effect=lambda **kw: None,
        ),
        patch(
            "lca.infrastructure.session.emit.lifecycle_emit.checkpoint",
            side_effect=lambda status, **kw: checkpoint_kwargs.append(
                {"status": status, **kw}
            ),
        ),
        patch(
            "lca.infrastructure.session.emit.lifecycle_emit.persist_approval",
            side_effect=lambda *args, **kw: None,
        ),
        patch(
            "lca.plugins.session.runtime.resume.point.serialize_resume_point",
            return_value={},
        ),
        patch(
            "lca.plugins.session.runtime.resume.point.resume_point_from_state_snapshot",
            return_value=object(),
        ),
    ):
        from lca.infrastructure.session.emit.lifecycle_emit import (
            emit_approval_pause_from_result,
        )

        emit_approval_pause_from_result(result)
    assert len(checkpoint_kwargs) == 1
    return checkpoint_kwargs[0]["pending_tools_calling"]


def _events_via_recovery(approval_request: dict[str, Any]) -> list[Any]:
    captured: list[Any] = []
    with (
        patch(
            "lca.infrastructure.session.emit.lifecycle_emit.resolve_run_session_writer",
            return_value=object(),
        ),
        patch(
            "lca.loop.fact_gateway.append_catalog_bound",
            side_effect=lambda event, **kw: captured.append(event),
        ),
    ):
        from lca.plugins.transport.webserver.carrier.runs.recovery import (
            _seed_recovery_facts,
        )

        _seed_recovery_facts(
            object(),
            {"approval_id": "plan:intervene.interrupt:1"},
            {
                "run_id": "run_test",
                "approval_request": approval_request,
            },
        )
    return captured


def test_fresh_and_recovery_paths_derive_identical_pending_lists() -> None:
    fresh_pending = _pending_via_fresh_pause(deepcopy(_APPROVAL_REQUEST))
    recovery_pending = _pending_via_recovery(deepcopy(_APPROVAL_REQUEST))
    assert recovery_pending == fresh_pending
    assert fresh_pending == [
        {
            "tool_name": "askUserQuestion",
            "call_id": "toolu_1",
            "arguments": {
                "questions": [{"question": "name"}],
                "lca_run_id": "run_test",
            },
        },
        {
            "tool_name": "runBash",
            "call_id": "toolu_2",
            "arguments": {"cmd": "ls"},
        },
    ]


def _pending_via_recovery(
    approval_request: dict[str, Any],
) -> list[dict[str, Any]]:
    for event in _events_via_recovery(approval_request):
        if type(event).__name__ == "SessionCheckpoint":
            return event.pending_tools_calling
    raise AssertionError("recovery did not emit a SessionCheckpoint")


def test_recovery_journal_stays_minimal_no_step_records() -> None:
    """ADR-0195 P4-S04: recovery seeds approval.persisted.v1 + waiting_input
    only; the pause-time journal.json is the historical record."""
    events = _events_via_recovery(deepcopy(_APPROVAL_REQUEST))
    assert [type(e).__name__ for e in events] == [
        "ApprovalPersisted",
        "SessionCheckpoint",
    ]
