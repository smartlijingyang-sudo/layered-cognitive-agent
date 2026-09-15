"""Tests for phase.think.context.compact plugin.

Verifies the typed ``think.context.compact`` node that lifts the
off-graph context-compaction step into a typed-boundary node. Reads
``writer`` (presence check) + ``state`` (``AgentState.budget`` and
``state.retrieved_context``) and emits a ``CompactReceipt`` plus a
``RoutingDecision`` typed port.

Spec: ``docs/superpowers/specs/2026-09-15-pr3.8-borrowed-nodes-design.md``
§2.2. ADR-0195 §1.4 / C13 frozen+forbid contract on the receipt.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.dto.compact_receipt import CompactReceipt
from lca.contracts.models.core.state.state import Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.think.context_compact import ThinkContextCompactExecutor


def _ctx() -> NodeContext:
    """Minimal NodeContext; the compact node does not read runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


@dataclass
class _StateStub:
    """Typed mock for ``AgentState`` exposing only the fields the node reads."""

    budget: Budget
    retrieved_context: list[object] | None = None


def _state(
    *,
    budget: Budget,
    retrieved_context: list[object] | None = None,
) -> _StateStub:
    return _StateStub(budget=budget, retrieved_context=retrieved_context)


# A presence placeholder for the ``writer`` port. The node never calls
# any writer method; the port exists so the typed-boundary contract
# is honored (downstream nodes that consume ``compact_receipt`` can
# rely on the writer being present on the think waterfall).
_WRITER_PRESENT: object = object()


@pytest.mark.asyncio
async def test_context_compact_under_threshold_emits_noop() -> None:
    """Ratio < 0.7 -> ``CompactReceipt.noop`` and forward to history.assemble."""
    executor = ThinkContextCompactExecutor()
    budget = Budget(
        max_tokens=1000,
        max_steps=None,
        used_tokens=10,
        used_steps=0,
        used_cost_usd=0.0,
    )
    payload = [f"record-{i}" for i in range(5)]
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "writer": _WRITER_PRESENT,
                "state": _state(budget=budget, retrieved_context=payload),
            }
        ),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    routing: RoutingDecision = output.port_values["routing"]

    assert isinstance(receipt, CompactReceipt)
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert receipt.bytes_before == receipt.bytes_after
    assert routing.action_type == ActionType.RESPOND
    assert routing.next_node == "think.history.assemble"
    assert routing.next_hint == "compact_noop"


@pytest.mark.asyncio
async def test_context_compact_over_threshold_emits_applied_receipt() -> None:
    """Ratio >= 0.7 -> ``CompactReceipt.applied(truncate_oldest)`` + history.assemble."""
    executor = ThinkContextCompactExecutor()
    budget = Budget(
        max_tokens=100,
        max_steps=None,
        used_tokens=80,  # ratio = 0.8, above the 0.7 gate
        used_steps=0,
        used_cost_usd=0.0,
    )
    payload = ["x" * 50, "y" * 50, "z" * 50]
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "writer": _WRITER_PRESENT,
                "state": _state(budget=budget, retrieved_context=payload),
            }
        ),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    routing: RoutingDecision = output.port_values["routing"]

    assert receipt.compacted is True
    assert receipt.strategy == "truncate_oldest"
    assert receipt.bytes_after < receipt.bytes_before
    assert receipt.bytes_after > 0
    assert routing.next_node == "think.history.assemble"
    assert routing.next_hint == "compact_done"


@pytest.mark.asyncio
async def test_context_compact_missing_writer_returns_empty_output() -> None:
    """Missing ``writer`` port -> empty ``NodeOutput`` (fail loud, not silent pass)."""
    executor = ThinkContextCompactExecutor()
    budget = Budget(max_tokens=100, used_tokens=80)
    payload = ["x" * 50, "y" * 50]
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                # ``writer`` deliberately absent
                "state": _state(budget=budget, retrieved_context=payload),
            }
        ),
    )
    assert output.port_values == {}


@pytest.mark.asyncio
async def test_context_compact_is_idempotent() -> None:
    """Same ``(writer, state)`` -> same stable fields on receipt + routing (C9).

    ``CompactReceipt.at`` is the per-call UTC timestamp, so two calls
    produce different ``at`` values by construction. The idempotency
    contract compares every other field on the receipt and the full
    ``RoutingDecision`` value (which is fully deterministic).
    """
    executor = ThinkContextCompactExecutor()
    budget = Budget(max_tokens=100, used_tokens=80)
    payload = ["alpha", "beta", "gamma", "delta"]
    port_values = {
        "writer": _WRITER_PRESENT,
        "state": _state(budget=budget, retrieved_context=payload),
    }

    out_a = await executor.node_execute(_ctx(), NodeInput(port_values=port_values))
    out_b = await executor.node_execute(_ctx(), NodeInput(port_values=port_values))

    receipt_a: CompactReceipt = out_a.port_values["compact_receipt"]
    receipt_b: CompactReceipt = out_b.port_values["compact_receipt"]
    assert receipt_a.compacted == receipt_b.compacted
    assert receipt_a.strategy == receipt_b.strategy
    assert receipt_a.bytes_before == receipt_b.bytes_before
    assert receipt_a.bytes_after == receipt_b.bytes_after
    assert out_a.port_values["routing"] == out_b.port_values["routing"]

    # Two fresh executors must also agree: no instance-level state.
    out_c = await ThinkContextCompactExecutor().node_execute(
        _ctx(), NodeInput(port_values=port_values)
    )
    out_d = await ThinkContextCompactExecutor().node_execute(
        _ctx(), NodeInput(port_values=port_values)
    )
    receipt_c: CompactReceipt = out_c.port_values["compact_receipt"]
    receipt_d: CompactReceipt = out_d.port_values["compact_receipt"]
    assert receipt_c.compacted == receipt_d.compacted
    assert receipt_c.strategy == receipt_d.strategy
    assert receipt_c.bytes_before == receipt_d.bytes_before
    assert receipt_c.bytes_after == receipt_d.bytes_after
    assert out_c.port_values["routing"] == out_d.port_values["routing"]


@pytest.mark.asyncio
async def test_context_compact_none_max_tokens_is_safe_noop() -> None:
    """``max_tokens is None`` -> ratio undefined -> noop, no exception."""
    executor = ThinkContextCompactExecutor()
    budget = Budget(
        max_tokens=None,
        max_steps=10,
        used_tokens=999,  # would explode the gate if compared to None
        used_steps=0,
    )
    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "writer": _WRITER_PRESENT,
                "state": _state(budget=budget, retrieved_context=["a", "b", "c"]),
            }
        ),
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    routing: RoutingDecision = output.port_values["routing"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert routing.next_node == "think.history.assemble"
    assert routing.next_hint == "compact_noop"


@pytest.mark.asyncio
async def test_context_compact_exception_in_payload_size_routes_to_route_decide() -> None:
    """Compaction raises -> empty receipt + ``think.route.decide`` re-route.

    Forces the ``_payload_byte_size`` path to blow up via an unhashable
    element so the node's broad ``except Exception`` branch is
    exercised. The graph must see a typed empty receipt + a
    ``compact_skipped_error`` routing hint — never a raised exception.
    """
    executor = ThinkContextCompactExecutor()
    budget = Budget(max_tokens=100, used_tokens=80)

    class _ExplodingRepr:
        def __repr__(self) -> str:
            raise RuntimeError("boom")

    output = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "writer": _WRITER_PRESENT,
                "state": _state(
                    budget=budget,
                    retrieved_context=[_ExplodingRepr()],
                ),
            }
        ),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    routing: RoutingDecision = output.port_values["routing"]

    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert routing.next_node == "think.route.decide"
    assert routing.next_hint == "compact_skipped_error"
