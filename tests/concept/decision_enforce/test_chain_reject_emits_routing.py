"""Tests for ``gate.chain.reject`` typed-port contract.

ADR-0217 §3.3.3 + D4 typed-port cutover require every
decision-producing subgraph to emit a typed ``RoutingDecision``
on the ``routing`` port. ``gate.chain.reject`` is the inner-graph
terminal of ``concept.decision.enforce`` (think.gate's
``sub_spec_ref``); its outputs drive the outer
``phase_main_outer`` edge selector (``think.main -> terminal.commit``
when ``routing.action_type == "respond"``).

Regression: respond-with-text runs were silently misclassified as
``StopDecision(reason=ERROR)`` because ``gate.chain.reject`` never
wrote the ``routing`` port, the outer edge selector found no match,
``think.main`` terminated, and ``terminal.commit`` was never visited.
The terminal driver then fell back to ERROR.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.concept.decision_enforce.chain_reject.chain_reject import (
    GateChainRejectExecutor,
)


def _ctx() -> NodeContext:
    return NodeContext(
        runtime={},
        budget={},
        metadata={"plan_ref": "concept.decision.enforce", "node_id": "gate.chain.reject"},
    )


def _decision(action_type: str = "respond", decision_id: str = "dec_in") -> Decision:
    return Decision(  # type: ignore[call-arg]
        decision_id=decision_id,
        action_type=action_type,
        rationale="r",
        confidence=1.0,
    )


@pytest.mark.asyncio
async def test_chain_reject_emits_routing_port() -> None:
    """``gate.chain.reject`` must emit ``routing`` on its declared outputs."""
    candidate = _decision("respond", "dec_in")
    enforced = _decision("respond", "dec_in")
    out = await GateChainRejectExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"decision": candidate, "enforced_decision": enforced}),
    )
    assert "routing" in out.port_values, (
        "gate.chain.reject must emit a typed RoutingDecision on the routing port; "
        "without it, the outer edge selector cannot route think.main to "
        "terminal.commit and every RESPOND run is misclassified as ERROR."
    )
    routing = out.port_values["routing"]
    assert isinstance(routing, RoutingDecision)
    assert routing.action_type == "respond"


@pytest.mark.asyncio
async def test_chain_reject_declares_routing_in_outputs() -> None:
    """``declared_outputs`` must include ``routing`` (typed port contract)."""
    assert "routing" in GateChainRejectExecutor().declared_outputs, (
        "GateChainRejectExecutor.declared_outputs must declare the routing port "
        "per D4 typed-port contract; otherwise the graph lifter refuses to wire it."
    )
