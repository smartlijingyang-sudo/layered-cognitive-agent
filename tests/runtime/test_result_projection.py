from __future__ import annotations

import pytest

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.terminal_outcome import (
    ErrorRef,
    ResumeCursor,
    TerminalOutcome,
    TerminalOutcomeKind,
    TextRef,
)
from lca.contracts.protocols.declarative_phase_graph import (
    DeclarativeRunOutcome,
    DeclarativeValidationError,
    PhaseRunCursor,
)
from lca.runtime.result_projection import TerminalResultProjection


class _StateStore:
    def __init__(self, state_ref: str = "state://saved") -> None:
        self._state_ref = state_ref
        self.saved: list[AgentState] = []

    async def save(self, state: AgentState) -> str:
        self.saved.append(state)
        return self._state_ref


def _state() -> AgentState:
    return AgentState(trace_id="trace-1", task="project result", budget=Budget())


def _cursor() -> PhaseRunCursor:
    return PhaseRunCursor(
        plan_ref="plan-1",
        node_id="think.standard",
        visit_counts=(("think.standard", 1),),
        edge_counts=(),
        artifacts={},
        causation_refs=(),
        budget_snapshot={},
    )


@pytest.mark.asyncio
async def test_terminal_projection_derives_completed_result_from_terminal_fact() -> None:
    store = _StateStore()
    terminal = TerminalOutcome(
        kind=TerminalOutcomeKind.COMPLETED,
        stop_reason="task_done",
        final_output_ref=TextRef(text="completed output"),
        plan_ref="plan-1",
        journal_seq_end=12,
    )

    result = await TerminalResultProjection(store).project(
        _state(),
        terminal_outcome=terminal,
        declarative_outcome=None,
    )

    assert result.status is TaskStatus.COMPLETED
    assert result.output == "completed output"
    assert result.final_state_ref == "state://saved"
    assert result.extra["plan_ref"] == "plan-1"
    assert result.extra["journal_seq_end"] == 12
    assert result.extra["terminal_outcome_kind"] == "completed"
    assert len(store.saved) == 1


@pytest.mark.asyncio
async def test_terminal_projection_keeps_pause_resume_data_in_one_result() -> None:
    store = _StateStore()
    cursor = _cursor()
    terminal = TerminalOutcome(
        kind=TerminalOutcomeKind.WAITING_INPUT,
        stop_reason="approval_required",
        resume_cursor=ResumeCursor(cursor="resume-think", session_seq=7, approval_id="approval-1"),
        plan_ref="plan-1",
        journal_seq_end=12,
    )
    declarative = DeclarativeRunOutcome(
        kind="paused",
        cursor=cursor,
        stop=object(),
        approval_request={"approval_id": "approval-1", "type": "tool_approval"},
    )

    result = await TerminalResultProjection(store).project(
        _state(),
        terminal_outcome=terminal,
        declarative_outcome=declarative,
    )

    assert result.status is TaskStatus.INPUT_REQUIRED
    assert result.extra["state_ref"] == "state://saved"
    assert result.extra["resume_cursor"] == {
        "cursor": "resume-think",
        "session_seq": 7,
        "approval_id": "approval-1",
    }
    assert result.extra["approval_request"] == {
        "approval_id": "approval-1",
        "type": "tool_approval",
    }
    assert result.extra["phase_cursor"] == cursor
    assert result.extra["state_snapshot"].state_ref == "state://saved"


@pytest.mark.asyncio
async def test_terminal_projection_derives_failed_result_from_terminal_fact() -> None:
    store = _StateStore()
    terminal = TerminalOutcome(
        kind=TerminalOutcomeKind.FAILED,
        stop_reason="execution_error",
        error_ref=ErrorRef(kind="execution_error", message="tool execution failed"),
        plan_ref="plan-1",
        journal_seq_end=12,
    )

    result = await TerminalResultProjection(store).project(
        _state(),
        terminal_outcome=terminal,
        declarative_outcome=DeclarativeRunOutcome(
            kind="failed",
            cursor=_cursor(),
            stop=object(),
        ),
    )

    assert result.status is TaskStatus.FAILED
    assert result.error == "tool execution failed"
    assert result.final_state_ref == "state://saved"
    assert result.extra["terminal_outcome_kind"] == "failed"


@pytest.mark.asyncio
async def test_terminal_projection_rejects_unpersisted_waiting_input() -> None:
    terminal = TerminalOutcome(
        kind=TerminalOutcomeKind.WAITING_INPUT,
        stop_reason="approval_required",
        resume_cursor=ResumeCursor(cursor="resume-think", session_seq=7, approval_id="approval-1"),
        plan_ref="plan-1",
        journal_seq_end=12,
    )

    with pytest.raises(
        DeclarativeValidationError,
        match="waiting input requires a durable StateStore",
    ):
        await TerminalResultProjection(None).project(
            _state(),
            terminal_outcome=terminal,
            declarative_outcome=None,
        )
