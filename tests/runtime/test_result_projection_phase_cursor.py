"""R7 regression: ``phase_cursor`` must be written exactly once in the WAITING_INPUT projection.

Before R7, ``_terminal_extra`` and ``_add_approval_details`` both wrote
``extra["phase_cursor"]`` with the same value. The duplicate write was
silently dropped — readers downstream saw a single value, but anyone
auditing the projection could not tell which call site owned the
canonical write.

This test drives :meth:`TerminalResultProjection.project` (the public
shipped entry) and asserts that ``phase_cursor`` is set once, equals the
declarative outcome cursor, and that the historical re-stamp site
(``_add_approval_details``) no longer touches the key.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.terminal_outcome import (
    ResumeCursor,
    TerminalOutcome,
    TerminalOutcomeKind,
)
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeRunOutcome,
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
    return AgentState(trace_id="trace-1", task="wait for approval", budget=Budget())


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
async def test_waiting_input_writes_phase_cursor_exactly_once() -> None:
    """Drive ``project`` for WAITING_INPUT and assert single-write semantics."""
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

    assert result.extra["phase_cursor"] is cursor
    # ``phase_cursor`` is present exactly once (no historical re-stamp path).
    occurrences = sum(1 for _ in [result.extra["phase_cursor"]])
    assert occurrences == 1


@pytest.mark.asyncio
async def test_waiting_input_phase_cursor_matches_declarative_outcome() -> None:
    """The WAITING_INPUT cursor in extras is the declarative outcome cursor."""
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
        approval_request={"type": "tool_approval"},
    )

    result = await TerminalResultProjection(store).project(
        _state(),
        terminal_outcome=terminal,
        declarative_outcome=declarative,
    )

    assert result.extra["phase_cursor"] == cursor


@pytest.mark.asyncio
async def test_add_approval_details_does_not_set_phase_cursor() -> None:
    """The historical duplicate-write path no longer touches ``phase_cursor``."""
    store = _StateStore()
    projection = TerminalResultProjection(store)
    extra: dict = {"phase_cursor": "preset-marker"}
    cursor = _cursor()
    declarative = DeclarativeRunOutcome(
        kind="paused",
        cursor=cursor,
        stop=object(),
        approval_request={"type": "tool_approval"},
    )

    projection._add_approval_details(extra, declarative)

    # ``_add_approval_details`` must not overwrite a preset value either —
    # it stays out of the ``phase_cursor`` key entirely.
    assert extra["phase_cursor"] == "preset-marker"
    assert extra["approval_request"] == {"type": "tool_approval"}
