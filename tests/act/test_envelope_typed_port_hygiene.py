"""ADR-0235 / PR-5: act.envelope typed-port hygiene — state / decision off metadata.

The ``act.envelope`` node (``lca/nodes/act/envelope/envelope.py``) used
to smuggle ``state`` and ``decision`` through ``envelope.metadata``.
That violated ADR-0195 §1.4 C13 (typed Contract across boundary =
fail-loud; ``metadata: dict[str, Any]`` is the typed-port anti-pattern)
and the C2 双平面 (envelope is the effect-gateway 单据, not cognition's
state carrier).

This module pins:

- ``metadata`` no longer contains ``state`` or ``decision``.
- The envelope's typed inputs are ``(decision, state)``; outputs are
  ``(envelope, decision, state)`` (passthrough for the downstream
  nodes that need to keep forwarding typed ports).
- The envelope does NOT read ``context.runtime.state`` — the act business
  layer no longer reaches into the graph runtime.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.nodes.act.envelope.envelope import ActEnvelopeExecutor


def _ctx() -> NodeContext:
    return NodeContext(
        runtime={},
        budget={},
        metadata={"plan_ref": "plan-xyz", "node_id": "act.envelope"},
    )


@pytest.mark.asyncio
async def test_envelope_metadata_does_not_contain_state_or_decision() -> None:
    """ADR-0235 / PR-5: state / decision leave the envelope's metadata.

    ``metadata`` is restricted to op-relative fields (``effect_class`` /
    ``operation``) so the envelope remains a single effect-gateway
    单据, not a cognition-state carrier.
    """
    decision = Decision(
        decision_id=new_id("dec"),
        action_type="use_tool",
        rationale="r",
        confidence=1.0,
    )
    state = AgentState(
        trace_id="trace-xyz",
        task="task-xyz",
        budget=Budget(),
    )
    node = ActEnvelopeExecutor()

    out: NodeOutput = await node.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": decision, "state": state}),
    )

    envelope = out.port_values["envelope"]
    assert "state" not in envelope.metadata
    assert "decision" not in envelope.metadata
    assert envelope.metadata == {"effect_class": "tools", "operation": "body.act"}


@pytest.mark.asyncio
async def test_envelope_passes_decision_and_state_through_typed_ports() -> None:
    """``decision`` and ``state`` flow through typed ports, not metadata."""
    decision = Decision(
        decision_id=new_id("dec"),
        action_type="use_tool",
        rationale="r",
        confidence=1.0,
    )
    state = AgentState(
        trace_id="trace-xyz",
        task="task-xyz",
        budget=Budget(),
    )
    node = ActEnvelopeExecutor()

    out = await node.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": decision, "state": state}),
    )

    # typed-port passthrough identity
    assert out.port_values["decision"] is decision
    assert out.port_values["state"] is state


@pytest.mark.asyncio
async def test_envelope_does_not_read_context_runtime_state() -> None:
    """The act business layer does not peek at ``context.runtime.state``.

    Even when ``context.runtime`` is a sentinel object that would raise
    on attribute access, the node must succeed (state arrives via
    typed port).
    """

    class RaisingRuntime:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(
                f"act.envelope must not reach into context.runtime.{name} "
                f"(ADR-0235 / PR-5 「act 业务不知道图存在」boundary)"
            )

    decision = Decision(
        decision_id=new_id("dec"),
        action_type="use_tool",
        rationale="r",
        confidence=1.0,
    )
    node = ActEnvelopeExecutor()

    out = await node.node_execute(
        NodeContext(
            runtime=RaisingRuntime(),
            budget={},
            metadata={"plan_ref": "plan-xyz", "node_id": "act.envelope"},
        ),
        NodeInput(port_values={"decision": decision, "state": None}),
    )
    assert out.port_values["envelope"] is not None


@pytest.mark.asyncio
async def test_envelope_rejects_non_decision_input() -> None:
    """Non-``Decision`` on ``decision`` port raises ``TypeError``."""
    node = ActEnvelopeExecutor()
    with pytest.raises(TypeError, match=r"act\.envelope"):
        await node.node_execute(
            _ctx(),
            NodeInput(port_values={"decision": "not a decision", "state": None}),
        )


@pytest.mark.asyncio
async def test_envelope_rejects_non_state_input() -> None:
    """Non-``AgentState`` (and non-None) on ``state`` port raises ``TypeError``."""
    node = ActEnvelopeExecutor()
    decision = Decision(
        decision_id=new_id("dec"),
        action_type="use_tool",
        rationale="r",
        confidence=1.0,
    )
    with pytest.raises(TypeError, match=r"act\.envelope"):
        await node.node_execute(
            _ctx(),
            NodeInput(port_values={"decision": decision, "state": "not a state"}),
        )
