"""Regression tests for unified terminal fact construction at runtime finalization."""

from __future__ import annotations

import pytest

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeRunOutcome,
    PhaseRunCursor,
)
from lca.harness.declarative.execute.outcome_projection import InterpretationResult
from lca.plugins.runtime.reducer import DefaultReducer
from lca.runtime.result_finalizer import RuntimeResultFinalizer


class _Hooks:
    async def trigger(self, event_name: str, state: AgentState) -> None:
        return None


class _ArtifactClosure:
    def synthesize(self) -> str | None:
        return None


class _StateStore:
    async def save(self, state: AgentState) -> str:
        return "state://saved"


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
async def test_finalizer_projects_pause_from_one_terminal_fact() -> None:
    """A pause must not fall back to a separately derived carrier result."""

    cursor = _cursor()
    interpretation = InterpretationResult(
        state=AgentState(trace_id="trace-1", task="await approval", budget=Budget()),
        artifact=None,
        visits=(),
        facts=(),
        terminal_node="think.standard",
        cursor=cursor,
        outcome=DeclarativeRunOutcome(
            kind="paused",
            cursor=cursor,
            stop=StopDecision(should_stop=False, reason=StopReason.CONTINUE),
            approval_request={"approval_id": "approval-1", "type": "tool_approval"},
        ),
    )
    finalizer = RuntimeResultFinalizer(
        reducer=DefaultReducer(),
        hooks=_Hooks(),
        artifact_closure=_ArtifactClosure(),
        state_store=_StateStore(),
    )

    result = await finalizer.finalize(
        interpretation=interpretation,
        plan_ref="plan-1",
        journal_sequence=9,
    )

    assert result.status is TaskStatus.INPUT_REQUIRED
    assert result.extra["terminal_outcome_kind"] == "waiting_input"
    assert result.extra["resume_cursor"] == {
        "cursor": "think.standard",
        "session_seq": 9,
        "approval_id": "approval-1",
    }
    assert result.extra["phase_cursor"] == cursor
