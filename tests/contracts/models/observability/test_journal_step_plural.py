from __future__ import annotations

from lca.contracts.models.observability.journal.step import (
    JournalStep,
    ToolCallRecord,
    ToolResult,
)


def test_tool_result_invocation_id() -> None:
    res = ToolResult(ok=True, latency_ms=10, invocation_id="inv_123")
    assert res.invocation_id == "inv_123"


def test_journal_step_plural_tools_bidirectional() -> None:
    tc1 = ToolCallRecord(invocation_id="inv_1", name="exportFile")
    tc2 = ToolCallRecord(invocation_id="inv_2", name="exportFile")
    tr1 = ToolResult(ok=True, latency_ms=5, invocation_id="inv_1")
    tr2 = ToolResult(ok=True, latency_ms=6, invocation_id="inv_2")

    # Plural initialization
    step_plural = JournalStep(
        step_id="step_001",
        step_index=1,
        phase="act",
        entered_at=100.0,
        tool_calls=(tc1, tc2),
        tool_results=(tr1, tr2),
    )
    assert len(step_plural.tool_calls) == 2
    assert len(step_plural.tool_results) == 2
    assert step_plural.tool_call == tc1
    assert step_plural.tool_result == tr1

    # Legacy singular initialization
    step_singular = JournalStep(
        step_id="step_002",
        step_index=2,
        phase="act",
        entered_at=100.0,
        tool_call=tc1,
        tool_result=tr1,
    )
    assert step_singular.tool_call == tc1
    assert step_singular.tool_result == tr1
    assert step_singular.tool_calls == (tc1,)
    assert step_singular.tool_results == (tr1,)
