"""Tests for phase.concept.act_subgraph.act_fanout plugin (PR-3.8.4).

Verifies the typed-boundary fan-out node that wires ``act.envelope →
act.fanout → act.dispatch`` with the 1:1 degenerate shape
(``envelopes[0] = envelope``). Per AGENTS.md §3 C10, the node orchestrates
``CommandEnvelope``s only — it must not execute.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.protocols.act.command.envelope import (
    CommandEnvelope,
    mint_envelope,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.act.fanout import ActFanoutExecutor


@dataclass
class _MockDecision:
    decision_id: str = "dec_test"


def _ctx() -> NodeContext:
    return NodeContext(runtime={}, budget={}, metadata={"plan_ref": "plan_test"})


def _envelope() -> CommandEnvelope:
    return mint_envelope(
        plan_ref="plan_test",
        scope_ref="run",
        decision=_MockDecision(),
        provider="effect.body",
    )


@pytest.mark.asyncio
async def test_act_fanout_emits_list_of_one_for_present_envelope() -> None:
    """Single envelope ⇒ list of length 1 with routing next_hint='fanout_1to1'."""
    executor = ActFanoutExecutor()
    envelope = _envelope()

    output = await executor.node_execute(_ctx(), NodeInput(port_values={"envelope": envelope}))

    envelopes = output.port_values["envelopes"]
    routing: RoutingDecision = output.port_values["routing"]

    assert isinstance(envelopes, list)
    assert len(envelopes) == 1
    assert routing.next_node == "act.dispatch"
    assert routing.next_hint == "fanout_1to1"


@pytest.mark.asyncio
async def test_act_fanout_emits_empty_list_for_missing_envelope() -> None:
    """Missing envelope ⇒ empty list with routing next_hint='fanout_empty'."""
    executor = ActFanoutExecutor()

    output = await executor.node_execute(_ctx(), NodeInput(port_values={}))

    envelopes = output.port_values["envelopes"]
    routing: RoutingDecision = output.port_values["routing"]

    assert envelopes == []
    assert routing.next_node == "act.dispatch"
    assert routing.next_hint == "fanout_empty"


@pytest.mark.asyncio
async def test_act_fanout_is_idempotent() -> None:
    """Same envelope input across repeated calls ⇒ identical outputs.

    Locks the AGENTS.md §3 C8 determinism guarantee for the typed-boundary
    carrier: no hidden state, no time/random/PID/env reads.
    """
    executor = ActFanoutExecutor()
    envelope = _envelope()
    node_input = NodeInput(port_values={"envelope": envelope})

    out_a = await executor.node_execute(_ctx(), node_input)
    out_b = await executor.node_execute(_ctx(), node_input)

    assert out_a.port_values["envelopes"] == out_b.port_values["envelopes"]
    assert out_a.port_values["routing"] == out_b.port_values["routing"]

    # Same property on the empty path.
    empty_input = NodeInput(port_values={})
    out_c = await executor.node_execute(_ctx(), empty_input)
    out_d = await executor.node_execute(_ctx(), empty_input)
    assert out_c.port_values["envelopes"] == out_d.port_values["envelopes"]
    assert out_c.port_values["routing"] == out_d.port_values["routing"]


@pytest.mark.asyncio
async def test_act_fanout_envelopes_first_equals_input_without_mutation() -> None:
    """``envelopes[0]`` is the same envelope as the input (identity + content).

    No construction, no wrapping, no mutation — the node is a typed-boundary
    carrier, not a mint. Content equality + identity locks the carrier
    contract.
    """
    executor = ActFanoutExecutor()
    envelope = _envelope()

    output = await executor.node_execute(_ctx(), NodeInput(port_values={"envelope": envelope}))

    envelopes = output.port_values["envelopes"]
    assert envelopes[0] is envelope
    assert envelopes[0] == envelope
    # Type assertion: the list element is the exact CommandEnvelope type.
    assert isinstance(envelopes[0], CommandEnvelope)
