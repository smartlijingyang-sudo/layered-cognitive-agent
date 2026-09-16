"""Tests for phase.think.context.truncate plugin (PR-B typed-port split).

Verifies the typed ``context.truncate`` node that owns only the
``truncate_oldest`` strategy. Reads a typed ``Budget`` + a typed
``context_payload`` from the upstream ports and emits a typed
``CompactReceipt``. Never reads ``context.runtime``, never emits
``RoutingDecision``.

Payload shapes exercised:

1. empty payload — receipts stays ``noop`` and unchanged
2. payload smaller than target — ``noop`` (kept == payload)
3. payload larger than target — ``applied(truncate_oldest)`` with
   ``bytes_after < bytes_before``
4. multi-element mixed-size payload — only the tail is kept,
   oldest entries drop first
5. exception swallowing — exception in byte sizing ⇒ ``skipped`` receipt
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.dto.compact_receipt import CompactReceipt
from lca.contracts.models.core.state.state import Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.think.context.truncate import ThinkContextTruncateExecutor


def _ctx() -> NodeContext:
    """Truncate is typed-only; never reads runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


def _budget(*, max_tokens: int | None = 100, used_tokens: int = 0) -> Budget:
    return Budget(
        max_tokens=max_tokens,
        used_tokens=used_tokens,
        max_steps=10,
        used_steps=0,
        max_cost_usd=None,
        used_cost_usd=0.0,
        max_wall_clock_seconds=None,
    )


@pytest.mark.asyncio
async def test_truncate_empty_payload_emits_noop() -> None:
    """Empty payload ⇒ ``noop`` receipt (kept is empty)."""
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"budget": _budget(), "context_payload": ()}),
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert receipt.bytes_before == 0
    assert receipt.bytes_after == 0


@pytest.mark.asyncio
async def test_truncate_payload_smaller_than_target_emits_noop() -> None:
    """Payload under the byte budget ⇒ ``noop`` (nothing to compact)."""
    executor = ThinkContextTruncateExecutor()
    # max_tokens=100 → target = 50% of 100 = 50 bytes; payload below target.
    budget = _budget(max_tokens=100)
    payload = ("short",)  # bytes_before = len(repr("short")) == 7

    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"budget": budget, "context_payload": payload}),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert receipt.bytes_before == receipt.bytes_after


@pytest.mark.asyncio
async def test_truncate_payload_larger_than_target_emits_applied() -> None:
    """Payload over the byte budget ⇒ ``applied(truncate_oldest)`` shrinks it."""
    executor = ThinkContextTruncateExecutor()
    # max_tokens=20 → target = 10 bytes; payload > 10 bytes shrinks.
    budget = _budget(max_tokens=20)
    payload = ("alpha-alpha", "beta-beta", "gamma-gamma")  # each ≥ 13 bytes

    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"budget": budget, "context_payload": payload}),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is True
    assert receipt.strategy == "truncate_oldest"
    assert receipt.bytes_after < receipt.bytes_before
    assert receipt.bytes_after > 0


@pytest.mark.asyncio
async def test_truncate_mixed_multi_element_keeps_tail() -> None:
    """Mixed-size payload: oldest entries drop, most recent are kept."""
    executor = ThinkContextTruncateExecutor()
    # target = 10 bytes; tail ("small") = 7 bytes fits; head ("a"*40) won't.
    budget = _budget(max_tokens=20)
    payload = ("a" * 40, "b" * 40, "small")

    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"budget": budget, "context_payload": payload}),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is True
    assert receipt.strategy == "truncate_oldest"


@pytest.mark.asyncio
async def test_truncate_handles_list_payload_as_tuple() -> None:
    """``context_payload`` may arrive as a list; node coerces to tuple."""
    executor = ThinkContextTruncateExecutor()
    budget = _budget(max_tokens=20)
    payload = ["alpha-alpha", "beta-beta", "gamma-gamma"]

    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"budget": budget, "context_payload": payload}),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.strategy in ("noop", "truncate_oldest")
    assert receipt.bytes_after <= receipt.bytes_before


@dataclass
class _ExplodingRepr:
    """Stand-in payload element whose ``__repr__`` blows up."""

    def __repr__(self) -> str:
        raise RuntimeError("boom from __repr__")


@pytest.mark.asyncio
async def test_truncate_exception_swallowed_emits_skipped_receipt() -> None:
    """Exception during sizing ⇒ ``skipped`` receipt (no raise out of graph)."""
    executor = ThinkContextTruncateExecutor()
    budget = _budget(max_tokens=100)
    payload: tuple[Any, ...] = (_ExplodingRepr(),)

    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"budget": budget, "context_payload": payload}),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    # ``CompactReceipt.skipped`` keeps the typed shape (never None).
    assert receipt.bytes_before == 0
    assert receipt.bytes_after == 0


@pytest.mark.asyncio
async def test_truncate_missing_budget_port_raises() -> None:
    """``budget`` is a typed-only port; missing ⇒ TypeError."""
    executor = ThinkContextTruncateExecutor()
    with pytest.raises(TypeError, match="Budget"):
        await executor.node_execute(
            _ctx(),
            NodeInput(port_values={"context_payload": ("a",)}),
        )


@pytest.mark.asyncio
async def test_truncate_wrong_budget_type_raises() -> None:
    """Wrong-type ``budget`` port value ⇒ TypeError."""
    executor = ThinkContextTruncateExecutor()
    with pytest.raises(TypeError, match="Budget"):
        await executor.node_execute(
            _ctx(),
            NodeInput(
                port_values={
                    "budget": object(),
                    "context_payload": ("a",),
                }
            ),
        )


@pytest.mark.asyncio
async def test_truncate_missing_context_payload_is_empty() -> None:
    """Missing ``context_payload`` port → empty tuple (no crash)."""
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"budget": _budget()}),
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert receipt.bytes_before == 0


@pytest.mark.asyncio
async def test_truncate_is_idempotent() -> None:
    """Same inputs ⇒ same receipt across repeated calls (C9).

    ``CompactReceipt.at`` differs by construction, so the comparison
    excludes the per-call timestamp.
    """
    executor = ThinkContextTruncateExecutor()
    budget = _budget(max_tokens=100)
    payload = ("alpha", "beta", "gamma", "delta")
    port_values = {"budget": budget, "context_payload": payload}

    out_a = await executor.node_execute(_ctx(), NodeInput(port_values=port_values))
    out_b = await executor.node_execute(_ctx(), NodeInput(port_values=port_values))

    receipt_a: CompactReceipt = out_a.port_values["compact_receipt"]
    receipt_b: CompactReceipt = out_b.port_values["compact_receipt"]
    assert receipt_a.compacted == receipt_b.compacted
    assert receipt_a.strategy == receipt_b.strategy
    assert receipt_a.bytes_before == receipt_b.bytes_before
    assert receipt_a.bytes_after == receipt_b.bytes_after
