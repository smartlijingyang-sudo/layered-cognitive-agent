"""StepNarrativeWriter 渲染全量 tool_calls 回归（run_04457e1757b1）。

同一 turn 发出 update_assistant_profile + update_identity 两个调用时，
旧 _render_step 只渲染单数 step.tool_call（首个），第二个调用在
journal.narrative.md 里"失踪"。
"""
from __future__ import annotations

from lca.contracts.models.observability import (
    JournalMetadata,
    JournalStep,
    StepContext,
    ToolCallRecord,
    ToolResult,
    append_step,
    close_document,
    empty_document,
)
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)


def test_both_tool_calls_rendered(tmp_path):
    meta = JournalMetadata(agent_role="agt_x", strategy_key="solo", plan_ref="plan_001", objective="t")
    doc = empty_document(run_id="r_x", trace_id="t_x", metadata=meta, started_at=1000.0)
    step = JournalStep(
        step_id="step_005",
        step_index=5,
        phase="act",
        entered_at=1000.0,
        exited_at=1001.0,
        duration_ms=1000,
        context_before=StepContext(objective="改名"),
        tool_calls=(
            ToolCallRecord(
                invocation_id="t1",
                name="update_assistant_profile",
                arguments={"display_name": "大内管家"},
                arguments_summary="改显示名",
            ),
            ToolCallRecord(
                invocation_id="t2",
                name="update_identity",
                arguments={"vibe": "干练"},
                arguments_summary="改风格",
            ),
        ),
        tool_results=(
            ToolResult(ok=True, latency_ms=10, invocation_id="t1"),
            ToolResult(ok=True, latency_ms=12, invocation_id="t2"),
        ),
    )
    doc = append_step(doc, step)
    doc = close_document(doc, outcome="completed", closed_at=1002.0)
    text = StepNarrativeWriter(tmp_path / "narrative.md").render(doc)
    assert "update_assistant_profile" in text
    assert "update_identity" in text
