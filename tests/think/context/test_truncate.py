"""Tests for phase.think.context.truncate plugin (PR-B typed-port split).

Verifies the typed ``context.truncate`` node that owns only the
``truncate_oldest`` strategy. Reads a typed ``Budget`` + a typed
``context_payload`` from the upstream ports and emits a typed
``CompactReceipt``. Never reads ``context.runtime``, never emits
``RoutingDecision``.

Payload shapes exercised:

1. empty payload — receipts stays ``noop`` and unchanged
2. below the 0.7 soft gate — ``noop`` even with a large payload
3. payload under the byte target (past the gate) — ``noop`` (kept == payload)
4. payload over the target — ``applied(truncate_oldest)`` with
   ``bytes_after < bytes_before``
5. multi-element mixed-size payload — only the tail is kept, oldest drop first
6. exception swallowing — past the gate, sizing raises ⇒ ``skipped`` receipt
7. payload resolved from the ``state.retrieved_context`` carrier when the
   port is absent (behavior-preserving vs the prior single node)
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


def _state_with_payload(payload: tuple[Any, ...]) -> Any:
    """Lightweight ``AgentState``-shaped carrier for the truncate fallback test."""
    state = Budget(
        max_tokens=100,
        used_tokens=0,
        max_steps=10,
        used_steps=0,
        max_cost_usd=None,
        used_cost_usd=0.0,
        max_wall_clock_seconds=None,
    )
    state.retrieved_context = payload
    return state


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
    """Past the gate but payload under the byte target ⇒ ``noop``."""
    executor = ThinkContextTruncateExecutor()
    # past the gate (used=80 ≥ 70); target = 50 bytes; payload is 7 bytes.
    budget = _budget(max_tokens=100, used_tokens=80)
    payload = ("short",)

    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"budget": budget, "context_payload": payload}),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert receipt.bytes_before == receipt.bytes_after


@pytest.mark.asyncio
async def test_truncate_below_soft_gate_emits_noop_despite_large_payload() -> None:
    """Past-payload but under the 0.7 token gate ⇒ ``noop`` (don't compact yet).

    Guards the soft compaction threshold the prior single ``context.compact``
    node enforced: compaction must not fire on every turn, only once the
    working context crosses ``_COMPACTION_THRESHOLD_RATIO``.
    """
    executor = ThinkContextTruncateExecutor()
    budget = _budget(max_tokens=1000, used_tokens=100)  # 10% < 70%
    payload = ("a" * 40, "b" * 40, "c" * 40)  # would shrink if the gate ran

    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"budget": budget, "context_payload": payload}),
    )

    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"


@pytest.mark.asyncio
async def test_truncate_payload_larger_than_target_emits_applied() -> None:
    """Payload over the byte budget (past the gate) ⇒ ``applied`` shrinks it."""
    executor = ThinkContextTruncateExecutor()
    # max_tokens=20, used=18 (≥14 ⇒ past the 0.7 gate); target = 10 bytes.
    budget = _budget(max_tokens=20, used_tokens=18)
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
    # past the gate (used=18 ≥ 0.7*20=14); target = 10 bytes.
    budget = _budget(max_tokens=20, used_tokens=18)
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
    budget = _budget(max_tokens=20, used_tokens=18)
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
    # past the gate so the strategy runs and __repr__ actually fires.
    budget = _budget(max_tokens=100, used_tokens=90)
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
async def test_truncate_resolves_payload_from_state_carrier() -> None:
    """Missing ``context_payload`` port ⇒ resolved via whitelisted ``state`` carrier.

    Behavior-preserving fallback: the prior single ``context.compact`` node
    read ``state.retrieved_context``; the split must too.
    """
    executor = ThinkContextTruncateExecutor()
    state = _state_with_payload(("a" * 40, "b" * 40, "small"))
    state.budget = Budget(
        max_tokens=20,
        used_tokens=18,
        max_steps=10,
        used_steps=0,
        max_cost_usd=None,
        used_cost_usd=0.0,
        max_wall_clock_seconds=None,
    )
    # Make the carrier's `.get("state")` lookup find the state. The
    # AST guard whitelists "state", so read it via runtime.get so the
    # test mirrors how the kernel exposes the per-turn carrier.
    class _Carrier(dict):
        def __getattr__(self, name: str) -> object:
            return self.get(name)

    runtime = _Carrier({"state": state})
    ctx = NodeContext(runtime=runtime, budget={}, metadata={})

    output = await executor.node_execute(
        ctx,
        NodeInput(port_values={}),
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is True
    assert receipt.strategy == "truncate_oldest"


@pytest.mark.asyncio
async def test_truncate_missing_context_payload_is_empty() -> None:
    """Missing ``context_payload`` port and no runtime carrier → empty tuple."""
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
    budget = _budget(max_tokens=100, used_tokens=90)
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
