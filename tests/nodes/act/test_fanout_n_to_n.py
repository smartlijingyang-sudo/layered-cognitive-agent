"""PR-3 (G-18, ADR-0232) — act.fanout N:N fanout with fanout_ntom next_hint.

The fanout node accepts an ``envelopes`` tuple (N:N typed port) and
emits ``next_hint="fanout_ntom"`` when ``len(envelopes) >= 2``.  The
single-envelope path is kept as a typed-port fallback that preserves
the historical ``fanout_1to1`` hint, and the empty path keeps
``fanout_empty``.  These tests pin each branch on the routing decision
so the closed-set enum never silently regresses.
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
from lca.nodes.act.fanout import (
    NEXT_HINT_FANOUT_1TO1,
    NEXT_HINT_FANOUT_EMPTY,
    NEXT_HINT_FANOUT_NTOM,
    ActFanoutExecutor,
)


@dataclass
class _MockDecision:
    decision_id: str = "dec_test"


def _ctx() -> NodeContext:
    return NodeContext(runtime={}, budget={}, metadata={"plan_ref": "plan_test"})


def _envelope(call_suffix: str = "") -> CommandEnvelope:
    return mint_envelope(
        plan_ref="plan_test",
        scope_ref=f"run_{call_suffix}" if call_suffix else "run",
        decision=_MockDecision(decision_id=f"dec_{call_suffix}" if call_suffix else "dec_test"),
        provider="effect.body",
    )


@pytest.mark.asyncio
async def test_fanout_zero_envelopes_emits_fanout_empty() -> None:
    """0 envelopes on the N:N port ⇒ fanout_empty (no routing change vs 1:1 path)."""

    executor = ActFanoutExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"envelopes": ()}),
    )

    envelopes = output.port_values["envelopes"]
    envelope = output.port_values["envelope"]
    routing: RoutingDecision = output.port_values["routing"]

    assert envelopes == []
    assert envelope is None
    assert routing.next_node == "act.dispatch"
    assert routing.next_hint == NEXT_HINT_FANOUT_EMPTY


@pytest.mark.asyncio
async def test_fanout_one_envelope_emits_fanout_1to1() -> None:
    """1 envelope on the N:N port ⇒ fanout_1to1 (back-compat)."""

    executor = ActFanoutExecutor()
    envelope = _envelope("solo")
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"envelopes": (envelope,)}),
    )

    envelopes = output.port_values["envelopes"]
    envelope_out = output.port_values["envelope"]
    routing: RoutingDecision = output.port_values["routing"]

    assert envelopes == [envelope]
    assert envelope_out is envelope
    assert routing.next_node == "act.dispatch"
    assert routing.next_hint == NEXT_HINT_FANOUT_1TO1


@pytest.mark.asyncio
async def test_fanout_n_envelopes_emits_fanout_ntom() -> None:
    """5 envelopes on the N:N port ⇒ fanout_ntom (PR-3 acceptance gate)."""

    executor = ActFanoutExecutor()
    envelopes_in = tuple(_envelope(str(i)) for i in range(5))
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"envelopes": envelopes_in}),
    )

    envelopes = output.port_values["envelopes"]
    envelope_out = output.port_values["envelope"]
    routing: RoutingDecision = output.port_values["routing"]

    assert len(envelopes) == 5
    assert envelopes == list(envelopes_in)
    assert envelope_out is envelopes_in[0]
    assert routing.next_node == "act.dispatch"
    assert routing.next_hint == NEXT_HINT_FANOUT_NTOM


@pytest.mark.asyncio
async def test_fanout_backcompat_single_envelope_port_still_works() -> None:
    """Caller passing the legacy ``envelope`` port keeps the 1:1 fanout_1to1 path."""

    executor = ActFanoutExecutor()
    envelope = _envelope("legacy")
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"envelope": envelope}),
    )

    envelopes = output.port_values["envelopes"]
    envelope_out = output.port_values["envelope"]
    routing: RoutingDecision = output.port_values["routing"]

    assert envelopes == [envelope]
    assert envelope_out is envelope
    assert routing.next_hint == NEXT_HINT_FANOUT_1TO1


@pytest.mark.asyncio
async def test_fanout_prefers_envelopes_port_over_envelope_port() -> None:
    """When both ports are populated, the N:N ``envelopes`` port wins (PR-3 invariant)."""

    executor = ActFanoutExecutor()
    solo = _envelope("solo")
    trio = tuple(_envelope(f"trio{i}") for i in range(3))
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"envelope": solo, "envelopes": trio}),
    )

    envelopes = output.port_values["envelopes"]
    routing: RoutingDecision = output.port_values["routing"]

    # The N:N port is authoritative when present; the legacy single-envelope
    # port is treated as a back-compat fallback only when ``envelopes`` is
    # absent.  This avoids ambiguity at the typed-port graph layer.
    assert envelopes == list(trio)
    assert routing.next_hint == NEXT_HINT_FANOUT_NTOM


@pytest.mark.asyncio
async def test_fanout_rejects_non_envelope_entry_in_envelopes_port() -> None:
    """A non-CommandEnvelope entry in the N:N port is rejected (typed contract)."""

    executor = ActFanoutExecutor()
    with pytest.raises(TypeError):
        await executor.node_execute(
            _ctx(),
            NodeInput(port_values={"envelopes": (_envelope("ok"), "not-an-envelope")}),
        )


@pytest.mark.asyncio
async def test_fanout_accepts_list_shaped_envelopes_port() -> None:
    """A list-typed ``envelopes`` value (typed-port adapter friendly) is accepted."""

    executor = ActFanoutExecutor()
    envelopes_in = [_envelope("a"), _envelope("b"), _envelope("c")]
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"envelopes": envelopes_in}),
    )

    assert len(output.port_values["envelopes"]) == 3
    assert output.port_values["routing"].next_hint == NEXT_HINT_FANOUT_NTOM
