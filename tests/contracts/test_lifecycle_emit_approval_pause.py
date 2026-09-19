"""Regression tests for HITL pause fact production.

The paused decision's tool calls must be recorded as ``step.tool_call.record``
(``status="pending_approval"``) before the ``waiting_input`` checkpoint, so
the gateway wire publishes ``tools_calling`` ahead of ``step_start``.
``askUserQuestion`` arguments gain ``lca_run_id`` for the frontend resume.
"""

from __future__ import annotations

from unittest.mock import patch

from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import Budget


def _paused_result() -> Result:
    return Result(
        trace_id="trace_1",
        status=TaskStatus.INPUT_REQUIRED,
        final_state_ref="mem://trace_1/0",
        total_steps=1,
        budget_used=Budget(),
        extra={
            "approval_request": {
                "approval_id": "plan:intervene.interrupt:1",
                "type": "ask_user_question",
                "questions": [{"question": "name"}],
                "tool_calls": [
                    {
                        "call_id": "toolu_1",
                        "tool_name": "askUserQuestion",
                        "arguments": {"questions": [{"question": "name"}]},
                    }
                ],
            },
            "state_snapshot": {"snapshot_id": "snap_1"},
        },
    )


class _FakeScope:
    run_id = "run_test"


def test_approval_pause_records_pending_tool_call_before_checkpoint() -> None:
    calls: list[dict] = []
    checkpoint_kwargs: list[dict] = []
    persist_calls: list[dict] = []

    def fake_record(**kw):
        calls.append(kw)

    def fake_checkpoint(status: str, **kw):
        checkpoint_kwargs.append({"status": status, **kw})

    def fake_persist(*args, **kw):
        persist_calls.append({"args": args, **kw})

    with (
        patch(
            "lca.infrastructure.observability.facade.run.context.get_current_run_scope",
            return_value=_FakeScope(),
        ),
        patch(
            "lca.loop.commit.tool_journal.record_step_tool_call",
            side_effect=fake_record,
        ),
        patch(
            "lca.infrastructure.session.emit.lifecycle_emit.checkpoint",
            side_effect=fake_checkpoint,
        ),
        patch(
            "lca.infrastructure.session.emit.lifecycle_emit.persist_approval",
            side_effect=fake_persist,
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

        emit_approval_pause_from_result(_paused_result())

    assert len(calls) == 1
    call = calls[0]
    assert call["tool_name"] == "askUserQuestion"
    assert call["invocation_id"] == "toolu_1"
    assert call["status"] == "pending_approval"
    assert call["arguments"]["lca_run_id"] == "run_test"
    assert call["actor"] == "lifecycle"

    assert len(checkpoint_kwargs) == 1
    assert checkpoint_kwargs[0]["status"] == "waiting_input"
    pending = checkpoint_kwargs[0]["pending_tools_calling"]
    assert pending == [
        {
            "tool_name": "askUserQuestion",
            "call_id": "toolu_1",
            "arguments": {"questions": [{"question": "name"}], "lca_run_id": "run_test"},
        }
    ]

    # The tool identity must be recorded before the pause checkpoint so the
    # gateway pump publishes tools_calling ahead of the step_start pair.
    assert len(persist_calls) == 1  # persist_approval ran after the record


def test_approval_pause_uses_session_run_id_over_minted_resume_scope() -> None:
    """HIL resume mints a fresh observability RunScope; the frontend card must
    carry the session run id, not the minted child id, so the UI reattaches
    to the live stream."""
    calls: list[dict] = []

    class _MintedScope:
        run_id = "run_minted_child"

    def fake_record(**kw: object) -> None:
        calls.append(kw)

    with (
        patch(
            "lca.infrastructure.observability.facade.run.context.get_current_run_scope",
            return_value=_MintedScope(),
        ),
        patch(
            "lca.infrastructure.tools.run.finalizer.get_current_run_id",
            return_value="run_session",
        ),
        patch(
            "lca.loop.commit.tool_journal.record_step_tool_call",
            side_effect=fake_record,
        ),
        patch(
            "lca.infrastructure.session.emit.lifecycle_emit.checkpoint",
            side_effect=lambda status, **kw: None,
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

        emit_approval_pause_from_result(_paused_result())

    assert len(calls) == 1
    assert calls[0]["arguments"]["lca_run_id"] == "run_session"


def test_approval_pause_skips_tools_without_identity() -> None:
    calls: list[dict] = []
    checkpoint_kwargs: list[dict] = []

    result = _paused_result()
    result.extra["approval_request"]["tool_calls"] = [
        {"call_id": "", "tool_name": "askUserQuestion", "arguments": {}},
        {"call_id": "toolu_2", "tool_name": "", "arguments": {}},
    ]

    def fake_record(**kw):
        calls.append(kw)

    def fake_checkpoint(status: str, **kw):
        checkpoint_kwargs.append({"status": status, **kw})

    with (
        patch(
            "lca.infrastructure.observability.facade.run.context.get_current_run_scope",
            return_value=_FakeScope(),
        ),
        patch(
            "lca.loop.commit.tool_journal.record_step_tool_call",
            side_effect=fake_record,
        ),
        patch(
            "lca.infrastructure.session.emit.lifecycle_emit.checkpoint",
            side_effect=fake_checkpoint,
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

    assert calls == []
    assert checkpoint_kwargs[0]["pending_tools_calling"] is None
