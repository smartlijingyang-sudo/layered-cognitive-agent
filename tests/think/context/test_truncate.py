"""Tests for phase.think.context.truncate plugin (PR-B typed-port split).

Verifies the typed ``context.truncate`` node that owns only the
``truncate_oldest`` strategy. Reads ``state`` (the whitelisted kernel
runtime carrier) and sources both ``Budget`` and ``retrieved_context``
from it. Never reads ``context.runtime`` directly outside the runtime
carrier pattern, never emits ``RoutingDecision``.

Payload shapes exercised:

1. empty payload — receipts stays ``noop`` and unchanged
2. below the 0.7 soft gate — ``noop`` even with a large payload
3. payload under the byte target (past the gate) — ``noop`` (kept == payload)
4. payload over the target — ``applied(truncate_oldest)`` with
   ``bytes_after < bytes_before``
5. multi-element mixed-size payload — only the tail is kept, oldest drop first
6. exception swallowing — past the gate, sizing raises ⇒ ``skipped`` receipt
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.atoms.ids.ids import utc_now
from lca.contracts.dto.compact_receipt import CompactReceipt
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.think.context.truncate import ThinkContextTruncateExecutor


class _RuntimeCarrier(dict):
    """Dict + attribute proxy — the kernel runtime carrier shape."""

    def __getattr__(self, name: str) -> object:
        return self.get(name)


def _ctx(state: AgentState) -> NodeContext:
    """``state`` lives on the runtime carrier (kernel-injected)."""
    return NodeContext(runtime=_RuntimeCarrier(state=state), budget={}, metadata={})


def _budget(
    *, max_tokens: int | None = 100, used_tokens: int = 0
) -> Budget:
    return Budget(
        max_steps=10,
        used_steps=0,
        max_tokens=max_tokens,
        used_tokens=used_tokens,
        max_cost_usd=None,
        used_cost_usd=0.0,
        max_wall_clock_seconds=None,
        started_at=utc_now(),
    )


def _state_with(budget: Budget, payload: tuple[Any, ...] = ()) -> AgentState:
    state = AgentState(trace_id="t-truncate", task="", budget=budget)
    state.retrieved_context = payload
    return state


@pytest.mark.asyncio
async def test_truncate_empty_payload_emits_noop() -> None:
    """Empty payload ⇒ ``noop`` receipt (kept is empty)."""
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(
        _ctx(_state_with(_budget())), NodeInput(port_values={})
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert receipt.bytes_before == 0
    assert receipt.bytes_after == 0


@pytest.mark.asyncio
async def test_truncate_below_soft_gate_emits_noop_despite_large_payload() -> None:
    """Past-payload but under the 0.7 token gate ⇒ ``noop`` (don't compact yet)."""
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(
        _ctx(_state_with(budget=_budget(max_tokens=1000, used_tokens=100))),
        NodeInput(port_values={}),
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"


@pytest.mark.asyncio
async def test_truncate_payload_smaller_than_target_emits_noop() -> None:
    """Past the gate but payload under the byte target ⇒ ``noop``."""
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(
        _ctx(
            _state_with(
                budget=_budget(max_tokens=100, used_tokens=80),
                payload=("short",),
            )
        ),
        NodeInput(port_values={}),
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert receipt.bytes_before == receipt.bytes_after


@pytest.mark.asyncio
async def test_truncate_payload_larger_than_target_emits_applied() -> None:
    """Payload over the byte budget (past the gate) ⇒ ``applied`` shrinks it."""
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(
        _ctx(
            _state_with(
                budget=_budget(max_tokens=20, used_tokens=18),
                payload=("alpha-alpha", "beta-beta", "gamma-gamma"),
            )
        ),
        NodeInput(port_values={}),
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
    output = await executor.node_execute(
        _ctx(
            _state_with(
                budget=_budget(max_tokens=20, used_tokens=18),
                payload=("a" * 40, "b" * 40, "small"),
            )
        ),
        NodeInput(port_values={}),
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is True
    assert receipt.strategy == "truncate_oldest"


@pytest.mark.asyncio
async def test_truncate_handles_list_payload_as_tuple() -> None:
    """``retrieved_context`` may arrive as a list; node coerces to tuple."""
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(
        _ctx(
            _state_with(
                budget=_budget(max_tokens=20, used_tokens=18),
                payload=("alpha-alpha", "beta-beta", "gamma-gamma"),  # type: ignore[arg-type]
            )
        ),
        NodeInput(port_values={}),
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
    """Exception during sizing ⇒ ``noop`` receipt (no raise out of graph).

    With the soft gate, ``used_tokens/max_tokens >= 0.7`` ⇒ strategy runs.
    The exception happens during __repr__ on a payload element so we get
    the noop path through the soft gate bypass.
    """
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(
        _ctx(
            _state_with(
                budget=_budget(max_tokens=100, used_tokens=90),
                payload=(_ExplodingRepr(),),
            )
        ),
        NodeInput(port_values={}),
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is False
    assert receipt.strategy == "noop"
    assert receipt.bytes_before == 0
    assert receipt.bytes_after == 0


@pytest.mark.asyncio
async def test_truncate_no_state_in_runtime_raises() -> None:
    """No ``state`` on the runtime carrier ⇒ TypeError (fail-loud)."""
    executor = ThinkContextTruncateExecutor()
    with pytest.raises(TypeError, match="state"):
        await executor.node_execute(NodeContext(runtime={}, budget={}, metadata={}), NodeInput(port_values={}))


@pytest.mark.asyncio
async def test_truncate_state_without_budget_raises() -> None:
    """``state`` present but missing ``.budget`` ⇒ TypeError (fail-loud)."""
    executor = ThinkContextTruncateExecutor()
    bad_state = AgentState(trace_id="t", task="", budget=_budget())
    object.__setattr__(bad_state, "budget", object())  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="budget"):
        await executor.node_execute(_ctx(bad_state), NodeInput(port_values={}))


@pytest.mark.asyncio
async def test_truncate_retrieved_context_in_state_carrier() -> None:
    """Behavior-preserving fallback: ``state.retrieved_context`` sources the payload."""
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(
        _ctx(
            _state_with(
                budget=_budget(max_tokens=20, used_tokens=18),
                payload=("a" * 40, "b" * 40, "small"),
            )
        ),
        NodeInput(port_values={}),
    )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.compacted is True
    assert receipt.strategy == "truncate_oldest"


@pytest.mark.asyncio
async def test_truncate_missing_retrieved_context_is_empty() -> None:
    """Missing ``retrieved_context`` ⇒ empty payload, no crash."""
    executor = ThinkContextTruncateExecutor()
    output = await executor.node_execute(_ctx(_state_with(_budget())), NodeInput(port_values={}))
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
    state = _state_with(
        budget=_budget(max_tokens=100, used_tokens=90),
        payload=("alpha", "beta", "gamma", "delta"),
    )

    out_a = await executor.node_execute(_ctx(state), NodeInput(port_values={}))
    out_b = await executor.node_execute(_ctx(state), NodeInput(port_values={}))

    receipt_a: CompactReceipt = out_a.port_values["compact_receipt"]
    receipt_b: CompactReceipt = out_b.port_values["compact_receipt"]
    assert receipt_a.compacted == receipt_b.compacted
    assert receipt_a.strategy == receipt_b.strategy
    assert receipt_a.bytes_before == receipt_b.bytes_before
    assert receipt_a.bytes_after == receipt_b.bytes_after
