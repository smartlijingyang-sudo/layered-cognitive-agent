"""Tests for phase.concept.act_subgraph.act_join plugin (PR-3.8.5).

Verifies the typed-boundary join node that wires ``act.dispatch →
act.join → act.observe`` with the 1:1 degenerate shape
(``receipts[0] = receipt``). Per AGENTS.md §3 C10, the node orchestrates
``EffectReceipt`` lists only — it must not execute.
"""

from __future__ import annotations

import pytest

from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.act.join import ActJoinExecutor


def _ctx() -> NodeContext:
    return NodeContext(runtime={}, budget={}, metadata={"plan_ref": "plan_test"})


def _receipt(invocation_id: str = "inv_test") -> EffectReceipt:
    return EffectReceipt(
        invocation_id=invocation_id,
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key=f"idem_{invocation_id}",
        provider="effect.body",
    )


@pytest.mark.asyncio
async def test_act_join_emits_receipt_for_single_receipt() -> None:
    """Single receipt ⇒ pass-through with routing next_hint='join_1to1'.

    Locked 1:1 contract from PR-3.8.5 plan: ``receipts == [r]`` ⇒
    ``receipt is r`` and routing targets ``act.observe``.
    """
    executor = ActJoinExecutor()
    receipt = _receipt()

    output = await executor.node_execute(_ctx(), NodeInput(port_values={"receipts": [receipt]}))

    routed_receipt = output.port_values["receipt"]
    routing: RoutingDecision = output.port_values["routing"]

    assert routed_receipt is receipt
    assert isinstance(routed_receipt, EffectReceipt)
    assert routing.next_node == "act.observe"
    assert routing.next_hint == "join_1to1"


@pytest.mark.asyncio
async def test_act_join_emits_empty_output_for_empty_receipts() -> None:
    """Empty / missing receipts ⇒ empty NodeOutput (no port values).

    Empty path emits no ``receipt`` / ``routing`` so the bundle edge
    interpreter routes the empty payload downstream without forcing a
    decision the upstream never produced.
    """
    executor = ActJoinExecutor()

    output_empty = await executor.node_execute(_ctx(), NodeInput(port_values={"receipts": []}))
    assert output_empty.port_values == {}

    output_missing = await executor.node_execute(_ctx(), NodeInput(port_values={}))
    assert output_missing.port_values == {}


@pytest.mark.asyncio
async def test_act_join_rejects_parallel_receipts_in_v1() -> None:
    """Length > 1 ⇒ reject to terminal.commit, no receipt emitted.

    The N:N partial-failure policy is a follow-up PR; receiving
    ``len(receipts) > 1`` before that lands means upstream wiring violated
    the 1:1 invariant and the run must abort rather than silently pick
    one receipt.
    """
    executor = ActJoinExecutor()
    receipts = [_receipt("inv_a"), _receipt("inv_b")]

    output = await executor.node_execute(_ctx(), NodeInput(port_values={"receipts": receipts}))

    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.next_hint == "join_rejects_parallel_in_v1"
    assert "receipt" not in output.port_values


@pytest.mark.asyncio
async def test_act_join_is_idempotent() -> None:
    """Same receipts input across repeated calls ⇒ identical outputs.

    Locks the AGENTS.md §3 C8 determinism guarantee for the typed-boundary
    carrier: no hidden state, no time/random/PID/env reads.
    """
    executor = ActJoinExecutor()
    receipt = _receipt()

    single_input = NodeInput(port_values={"receipts": [receipt]})
    out_a = await executor.node_execute(_ctx(), single_input)
    out_b = await executor.node_execute(_ctx(), single_input)
    assert out_a.port_values == out_b.port_values

    empty_input = NodeInput(port_values={"receipts": []})
    out_c = await executor.node_execute(_ctx(), empty_input)
    out_d = await executor.node_execute(_ctx(), empty_input)
    assert out_c.port_values == out_d.port_values == {}

    reject_input = NodeInput(port_values={"receipts": [_receipt("inv_x"), _receipt("inv_y")]})
    out_e = await executor.node_execute(_ctx(), reject_input)
    out_f = await executor.node_execute(_ctx(), reject_input)
    assert out_e.port_values == out_f.port_values
