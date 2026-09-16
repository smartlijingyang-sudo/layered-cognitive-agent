"""PR-3 (G-20, ADR-0232) — act.envelope produces N envelopes from N tool_calls.

The constructor must fan a multi-call ``Decision`` into a tuple of
``CommandEnvelope`` instances (one per ``tool_calls`` entry).  The
legacy single-envelope port is preserved as a back-compat alias so
1:1 wiring continues to work.  These tests pin the cardinality
invariant on the typed-port surface.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.protocols.act.command.envelope import CommandEnvelope
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.act.envelope.envelope import ActEnvelopeExecutor


def _ctx() -> NodeContext:
    return NodeContext(
        runtime={"state": "running"},
        budget={"tokens": 1000},
        metadata={"plan_ref": "plan_test", "node_id": "node_test"},
    )


def _decision(tool_call_count: int) -> Decision:
    tool_calls = [
        ToolCall(call_id=f"call_{i}", tool_name=f"tool_{i}", arguments={})
        for i in range(tool_call_count)
    ]
    return Decision(
        decision_id="dec_test",
        action_type="use_tool",
        rationale="multi-call test",
        confidence=0.9,
        tool_calls=tool_calls,
    )


@pytest.mark.asyncio
async def test_act_envelope_one_tool_call_emits_one_envelope() -> None:
    """A Decision with exactly 1 tool_call yields envelopes=(e,) and envelope=e."""

    executor = ActEnvelopeExecutor()
    decision = _decision(1)

    output = await executor.node_execute(_ctx(), NodeInput(port_values={"decision": decision}))

    envelopes = output.port_values["envelopes"]
    envelope = output.port_values["envelope"]

    assert isinstance(envelopes, tuple)
    assert len(envelopes) == 1
    assert isinstance(envelopes[0], CommandEnvelope)
    assert envelope is envelopes[0]


@pytest.mark.asyncio
async def test_act_envelope_five_tool_calls_emits_five_envelopes() -> None:
    """A Decision with 5 tool_calls yields 5 envelopes; envelope aliases envelopes[0]."""

    executor = ActEnvelopeExecutor()
    decision = _decision(5)

    output = await executor.node_execute(_ctx(), NodeInput(port_values={"decision": decision}))

    envelopes = output.port_values["envelopes"]
    envelope = output.port_values["envelope"]

    assert isinstance(envelopes, tuple)
    assert len(envelopes) == 5
    assert all(isinstance(e, CommandEnvelope) for e in envelopes)
    assert envelope is envelopes[0]
    # Idempotency keys must NOT collide for the same decision — index suffix prevents this.
    keys = tuple(e.idempotency_key for e in envelopes)
    assert len(set(keys)) == 5


@pytest.mark.asyncio
async def test_act_envelope_zero_tool_calls_emits_empty_tuple() -> None:
    """A Decision with no tool_calls yields envelopes=() and envelope=None."""

    executor = ActEnvelopeExecutor()
    decision = _decision(0)

    output = await executor.node_execute(_ctx(), NodeInput(port_values={"decision": decision}))

    envelopes = output.port_values["envelopes"]
    envelope = output.port_values["envelope"]

    assert envelopes == ()
    assert envelope is None


@pytest.mark.asyncio
async def test_act_envelope_rejects_non_decision_input() -> None:
    """Non-Decision input is rejected by the typed-port contract."""

    executor = ActEnvelopeExecutor()
    with pytest.raises(TypeError):
        await executor.node_execute(_ctx(), NodeInput(port_values={"decision": "not-a-decision"}))
