"""Tests for region:intervene.interrupt plugin (ADR-0228 §Decision 4).

Verifies the typed ``intervene.interrupt`` node that converts an
upstream ``Decision`` + ``spine_seq`` into a typed ``Command`` plus a
``RoutingDecision(should_terminate=True)``. Five cases pin the
``action_type`` → ``Command.kind`` mapping, the ``decision_id`` pass-
through, the default ``issued_by="user"`` actor, and the
``issued_at_seq`` spine anchor.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.command import Command
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.intervene.interrupt.interrupt import InterruptExecutor


def _ctx() -> NodeContext:
    """Minimal NodeContext; interrupt is a pure transform of input ports."""
    return NodeContext(runtime={}, budget={}, metadata={})


def _decision(
    *,
    action_type: str = "ask_user",
    decision_id: str = "dec_001",
) -> Decision:
    """Build a Decision for the test (dataclass — kwargs only)."""
    return Decision(
        decision_id=decision_id,
        action_type=action_type,
        rationale="hitl pause",
        confidence=1.0,
    )


@pytest.mark.asyncio
async def test_interrupt_ask_user_emits_approve_command_and_terminates() -> None:
    """decision(action_type='ask_user') → Command(kind='approve'),
    RoutingDecision(should_terminate=True)."""
    executor = InterruptExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(action_type="ask_user"),
                "spine_seq": 7,
            }
        ),
    )
    cmd: Command = output.port_values["command"]
    routing: RoutingDecision = output.port_values["routing"]
    assert isinstance(cmd, Command)
    assert cmd.kind == "approve"
    assert routing.should_terminate is True


@pytest.mark.asyncio
async def test_interrupt_non_ask_user_emits_reject_command_and_terminates() -> None:
    """decision(action_type='respond') → Command(kind='reject'),
    RoutingDecision(should_terminate=True)."""
    executor = InterruptExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(action_type="respond"),
                "spine_seq": 11,
            }
        ),
    )
    cmd: Command = output.port_values["command"]
    routing: RoutingDecision = output.port_values["routing"]
    assert isinstance(cmd, Command)
    assert cmd.kind == "reject"
    assert routing.should_terminate is True


@pytest.mark.asyncio
async def test_interrupt_payload_carries_decision_id() -> None:
    """Command.payload['decision_id'] 是上游 Decision.decision_id 的透传。"""
    executor = InterruptExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(decision_id="dec_xyz_42"),
                "spine_seq": 1,
            }
        ),
    )
    cmd: Command = output.port_values["command"]
    assert cmd.payload == {"decision_id": "dec_xyz_42"}


@pytest.mark.asyncio
async def test_interrupt_issued_by_defaults_to_user() -> None:
    """v1 only ships the user-driven path; ``issued_by`` defaults to 'user'."""
    executor = InterruptExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(),
                "spine_seq": 3,
            }
        ),
    )
    cmd: Command = output.port_values["command"]
    assert cmd.issued_by == "user"


@pytest.mark.asyncio
async def test_interrupt_issued_at_seq_matches_input_spine_seq() -> None:
    """Command.issued_at_seq 与输入 spine_seq 端口一致(spine anchor)。"""
    executor = InterruptExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(),
                "spine_seq": 1024,
            }
        ),
    )
    cmd: Command = output.port_values["command"]
    assert cmd.issued_at_seq == 1024


@pytest.mark.asyncio
async def test_interrupt_routing_next_hint_points_to_resume() -> None:
    """RoutingDecision.next_hint 必须指向 intervene.resume(为下游恢复留路径)。"""
    executor = InterruptExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(),
                "spine_seq": 1,
            }
        ),
    )
    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_hint == "intervene.resume"


@pytest.mark.asyncio
async def test_interrupt_is_pure_across_instances() -> None:
    """两个独立构造的 executor 必须在相同输入下输出一致。

    Strengthens the brief's "no hidden state" requirement: equality
    across fresh instances proves the executor carries no instance-level
    state that leaks into subsequent outputs.
    """
    inp = NodeInput(
        port_values={
            "decision": _decision(decision_id="dec_pure"),
            "spine_seq": 5,
        }
    )
    out_a = await InterruptExecutor().node_execute(_ctx(), inp)
    out_b = await InterruptExecutor().node_execute(_ctx(), inp)
    assert out_a.port_values["command"] == out_b.port_values["command"]
    assert out_a.port_values["routing"] == out_b.port_values["routing"]
