"""DeliverySatisfiedGate tests (ADR-0196)."""

from __future__ import annotations

import pytest

from lca.cognition.brain.decision_gates.delivery.satisfied import DeliverySatisfiedGate
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.perceive.projection import PerceiveProjection
from lca.contracts.models.core.state.state import AgentState, Budget


@pytest.mark.asyncio
async def test_delivery_satisfied_rewrites_producer_tool_to_respond() -> None:
    manifest = ContextManifest(
        digest="d",
        items=(
            ContextItem(
                kind="workspace_artifacts",
                payload=[{"path": "graphplan_joke.png", "url": "/files/file_abcd"}],
                provenance="sensor.workspace-artifacts",
            ),
        ),
    )
    state = AgentState(
        trace_id="t",
        task="用python写一个图计划的笑话",
        budget=Budget(),
        perceive=PerceiveProjection(manifest=manifest, digest="d", step=1),
    )
    state.history.append(
        Turn(
            decision=Decision(
                decision_id="d0",
                action_type=ActionType.USE_TOOL,
                rationale="run",
                confidence=0.9,
                tool_calls=[ToolCall(call_id="c0", tool_name="executeCode", arguments={})],
            ),
            observation=Observation(observation_id="o0", success=True, payload={"ok": True}),
        )
    )
    gate = DeliverySatisfiedGate()
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="again",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c1", tool_name="executeCode", arguments={"code": "print(1)"})],
    )
    forced = await gate.enforce(state, decision)
    assert forced.action_type == ActionType.RESPOND


@pytest.mark.asyncio
async def test_delivery_satisfied_with_stdout_only() -> None:
    state = AgentState(
        trace_id="t",
        task="用python写一个图计划的笑话",
        budget=Budget(),
    )
    state.history.append(
        Turn(
            decision=Decision(
                decision_id="d0",
                action_type=ActionType.USE_TOOL,
                rationale="run",
                confidence=0.9,
                tool_calls=[ToolCall(call_id="c0", tool_name="executeCode", arguments={})],
            ),
            observation=Observation(
                observation_id="o0",
                success=True,
                payload={"stdout": "图计划笑话：Oct 31 == Dec 25！" + ("哈" * 40)},
            ),
        )
    )
    gate = DeliverySatisfiedGate()
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="again",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c1", tool_name="executeCode", arguments={"code": "print(1)"})],
    )
    forced = await gate.enforce(state, decision)
    assert forced.action_type == ActionType.RESPOND
    assert "Oct 31" in (forced.response_text or "")


@pytest.mark.asyncio
async def test_delivery_not_satisfied_allows_producer() -> None:
    state = AgentState(
        trace_id="t",
        task="用python写一个图计划的笑话",
        budget=Budget(),
    )
    gate = DeliverySatisfiedGate()
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="run",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c1", tool_name="executeCode", arguments={"code": "print(1)"})],
    )
    result = await gate.enforce(state, decision)
    assert result.action_type == ActionType.USE_TOOL


@pytest.mark.asyncio
async def test_delivery_satisfied_rewrites_listfiles_repeat_to_respond() -> None:
    """Inspect tools with substantive stdout count as delivery (listFiles-once scenario)."""
    file_list = '[{"name": ".lca", "type": "directory"}, {"name": "outputs", "type": "directory"}]'
    state = AgentState(
        trace_id="t",
        task="Use listFiles once on . then reply with file count only.",
        budget=Budget(),
    )
    state.history.append(
        Turn(
            decision=Decision(
                decision_id="d0",
                action_type=ActionType.USE_TOOL,
                rationale="list",
                confidence=0.9,
                tool_calls=[ToolCall(call_id="c0", tool_name="listFiles", arguments={"directoryPath": "."})],
            ),
            observation=Observation(
                observation_id="o0",
                success=True,
                payload={"stdout": file_list},
            ),
        )
    )
    gate = DeliverySatisfiedGate()
    decision = Decision(
        decision_id="d1",
        action_type=ActionType.USE_TOOL,
        rationale="list again",
        confidence=0.9,
        tool_calls=[ToolCall(call_id="c1", tool_name="listFiles", arguments={"directoryPath": "/mnt/data"})],
    )
    forced = await gate.enforce(state, decision)
    assert forced.action_type == ActionType.RESPOND
    assert file_list.strip() in (forced.response_text or "")
