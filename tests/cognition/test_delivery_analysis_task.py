"""Delivery gate: synthesis/analysis tasks must not treat raw stdout as delivery."""

from __future__ import annotations

import pytest

from lca.cognition.brain.decision_gates.delivery.satisfied import DeliverySatisfiedGate
from lca.cognition.convergence.evidence import build_delivery_evidence
from lca.cognition.convergence.payload import turn_has_delivery_signal
from lca.cognition.convergence.task_class import task_requires_synthesis
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.state.state import AgentState, Budget
from tests.support.session_gate_helpers import append_control_turn, bound_session


def test_task_requires_synthesis_detects_analysis_verbs() -> None:
    assert task_requires_synthesis("分析下这个文件")
    assert task_requires_synthesis("Please analyze this PDF")
    assert not task_requires_synthesis("Use listFiles once on . then reply with file count only.")


def test_analysis_task_stdout_is_not_delivery_signal() -> None:
    pdf_dump = "文档分析报告_客户标签体系\n" + ("段落内容。" * 20)
    assert not turn_has_delivery_signal(
        {"stdout": pdf_dump},
        task="分析下这个文件",
    )


def test_analysis_task_files_created_still_counts_as_delivery() -> None:
    assert turn_has_delivery_signal(
        {"stdout": "ignored"},
        files_created=("report.md",),
        task="分析下这个文件",
    )


def test_analysis_task_does_not_satisfy_delivery_evidence() -> None:
    pdf_dump = "文档分析报告_客户标签体系\n" + ("段落内容。" * 20)
    with bound_session("delivery-analysis"):
        state = AgentState(
            trace_id="t",
            task="分析下这个文件",
            budget=Budget(),
        )
        append_control_turn(
            state,
            Turn(
                decision=Decision(
                    decision_id="d0",
                    action_type=ActionType.USE_TOOL,
                    rationale="extract",
                    confidence=0.9,
                    tool_calls=[ToolCall(call_id="c0", tool_name="executeCode", arguments={})],
                ),
                observation=Observation(
                    observation_id="o0",
                    success=True,
                    payload={"stdout": pdf_dump},
                ),
            ),
        )
        evidence = build_delivery_evidence(state)
        assert evidence.satisfied is False
        assert evidence.has_user_visible_text is False


@pytest.mark.asyncio
async def test_analysis_task_delivery_gate_allows_another_tool() -> None:
    pdf_dump = "文档分析报告_客户标签体系\n" + ("段落内容。" * 20)
    with bound_session("delivery-analysis-gate"):
        state = AgentState(
            trace_id="t",
            task="分析下这个文件",
            budget=Budget(),
        )
        append_control_turn(
            state,
            Turn(
                decision=Decision(
                    decision_id="d0",
                    action_type=ActionType.USE_TOOL,
                    rationale="extract",
                    confidence=0.9,
                    tool_calls=[ToolCall(call_id="c0", tool_name="executeCode", arguments={})],
                ),
                observation=Observation(
                    observation_id="o0",
                    success=True,
                    payload={"stdout": pdf_dump},
                ),
            ),
        )
        gate = DeliverySatisfiedGate()
        decision = Decision(
            decision_id="d1",
            action_type=ActionType.USE_TOOL,
            rationale="think more",
            confidence=0.9,
            tool_calls=[ToolCall(call_id="c1", tool_name="executeCode", arguments={"code": "print(1)"})],
        )
        result = await gate.enforce(state, decision)
        assert result.action_type == ActionType.USE_TOOL
