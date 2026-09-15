"""Tests for phase.delegate.fold plugin.

Verifies the typed-boundary fold node that aggregates
``DelegationReceipt`` tuples into a ``FoldedDelegationResult`` plus an
updated ``Decision`` for the outer think phase.

ADR-0228 §Decision 5: typed contract is
``DelegationReceipt`` → ``FoldedDelegationResult`` + ``Decision``;
``decision.action_type`` flips between ``respond`` (all-ok) and
``use_tool`` (any non-ok receipt) so the body knows whether there is
still work to do.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.delegation import (
    DelegationReceipt,
    FoldedDelegationResult,
)
from lca.nodes.delegate.fold.fold import DelegateFoldExecutor


def _ctx() -> NodeContext:
    """Minimal NodeContext; fold node does not read runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


def _receipt(
    *,
    delegate_from: str,
    status: str = "ok",
    payload: dict[str, object] | None = None,
    error: str | None = None,
) -> DelegationReceipt:
    """Build a typed receipt for fixture use."""
    return DelegationReceipt(
        delegate_from=delegate_from,
        status=status,
        payload=payload,
        error=error,
    )


# ---------------------------------------------------------------------------
# Receipt counting / folding invariants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_ok_receipt_folds_to_one_ok_zero_error() -> None:
    """One receipt status='ok' → receipt_count=1, ok_count=1, error_count=0."""
    receipts = (_receipt(delegate_from="agent.a", payload={"answer": 42}),)
    output = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": receipts}),
    )

    folded: FoldedDelegationResult = output.port_values["folded_result"]
    assert isinstance(folded, FoldedDelegationResult)
    assert folded.receipt_count == 1
    assert folded.ok_count == 1
    assert folded.error_count == 0


@pytest.mark.asyncio
async def test_all_ok_receipts_produce_respond_decision() -> None:
    """2 receipts 全 ok → synthesised decision.action_type='respond'."""
    receipts = (
        _receipt(delegate_from="agent.a", payload={"answer": "a"}),
        _receipt(delegate_from="agent.b", payload={"answer": "b"}),
    )
    output = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": receipts}),
    )

    decision: Decision = output.port_values["decision"]
    assert isinstance(decision, Decision)
    assert decision.action_type == ActionType.RESPOND.value
    assert decision.action_type == "respond"

    folded: FoldedDelegationResult = output.port_values["folded_result"]
    assert folded.receipt_count == 2
    assert folded.ok_count == 2
    assert folded.error_count == 0


@pytest.mark.asyncio
async def test_any_error_receipt_produces_use_tool_decision() -> None:
    """1 receipt status='error' → action_type='use_tool', error_count=1."""
    receipts = (
        _receipt(
            delegate_from="agent.a",
            status="error",
            error="upstream timeout",
        ),
    )
    output = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": receipts}),
    )

    decision: Decision = output.port_values["decision"]
    assert decision.action_type == ActionType.USE_TOOL.value
    assert decision.action_type == "use_tool"

    folded: FoldedDelegationResult = output.port_values["folded_result"]
    assert folded.receipt_count == 1
    assert folded.error_count == 1
    assert folded.ok_count == 0


@pytest.mark.asyncio
async def test_mixed_receipts_route_to_use_tool() -> None:
    """Mixed ok/error/timeout still routes the body back to act."""
    receipts = (
        _receipt(delegate_from="agent.a", payload={"ok": True}),
        _receipt(delegate_from="agent.b", status="timeout", error="t/o"),
        _receipt(delegate_from="agent.c", payload={"ok": True}),
    )
    output = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": receipts}),
    )

    folded: FoldedDelegationResult = output.port_values["folded_result"]
    decision: Decision = output.port_values["decision"]
    assert folded.receipt_count == 3
    assert folded.ok_count == 2
    assert folded.error_count == 1  # timeout counts as non-ok
    assert decision.action_type == ActionType.USE_TOOL.value


# ---------------------------------------------------------------------------
# folded_payload invariants: receipts surface identity in
# folded_payload so the body can route per child.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_folded_payload_keys_are_delegate_from() -> None:
    """``folded_payload`` keys are the ``delegate_from`` of each receipt."""
    receipts = (
        _receipt(delegate_from="agent.a", payload={"answer": 1}),
        _receipt(delegate_from="agent.b", payload={"answer": 2}),
    )
    output = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": receipts}),
    )

    folded: FoldedDelegationResult = output.port_values["folded_result"]
    assert set(folded.folded_payload) == {"agent.a", "agent.b"}
    assert folded.folded_payload["agent.a"] == {"answer": 1}
    assert folded.folded_payload["agent.b"] == {"answer": 2}


@pytest.mark.asyncio
async def test_folded_payload_falls_back_to_error_dict() -> None:
    """Non-ok receipts surface ``{"error": ...}`` when no payload is set."""
    receipts = (_receipt(delegate_from="agent.a", status="error", error="boom"),)
    output = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": receipts}),
    )

    folded: FoldedDelegationResult = output.port_values["folded_result"]
    assert folded.folded_payload["agent.a"] == {"error": "boom"}


@pytest.mark.asyncio
async def test_decision_id_carries_first_delegate_from() -> None:
    """First receipt's ``delegate_from`` is surfaced in ``decision_id``."""
    receipts = (
        _receipt(delegate_from="agent.lead", payload={"answer": 1}),
        _receipt(delegate_from="agent.support", payload={"answer": 2}),
    )
    output = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": receipts}),
    )

    decision: Decision = output.port_values["decision"]
    assert decision.decision_id == "folded-agent.lead"


# ---------------------------------------------------------------------------
# Boundary cases: empty input and input-validation guard rails
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_receipts_default_to_respond() -> None:
    """Empty tuple → receipt_count=0, action_type='respond' (no body work)."""
    output = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": ()}),
    )

    folded: FoldedDelegationResult = output.port_values["folded_result"]
    decision: Decision = output.port_values["decision"]
    assert folded.receipt_count == 0
    assert folded.ok_count == 0
    assert folded.error_count == 0
    assert folded.folded_payload == {}
    assert decision.action_type == ActionType.RESPOND.value
    assert decision.decision_id == "folded-none"


@pytest.mark.asyncio
async def test_missing_port_default_to_empty() -> None:
    """Missing ``delegation_receipt`` port is treated as empty (no upstream)."""
    output = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={}),
    )

    folded: FoldedDelegationResult = output.port_values["folded_result"]
    decision: Decision = output.port_values["decision"]
    assert folded.receipt_count == 0
    assert decision.action_type == ActionType.RESPOND.value


@pytest.mark.asyncio
async def test_non_typed_receipt_is_rejected() -> None:
    """A bare ``dict`` in the receipt tuple must fail loud (C13 typed seam)."""
    with pytest.raises(TypeError, match="DelegationReceipt"):
        await DelegateFoldExecutor().node_execute(
            _ctx(),
            NodeInput(
                port_values={
                    "delegation_receipt": ({"delegate_from": "a", "status": "ok"},),
                }
            ),
        )


@pytest.mark.asyncio
async def test_non_tuple_receipt_payload_is_rejected() -> None:
    """A list at the top-level must fail loud (typed tuple contract)."""
    with pytest.raises(TypeError, match="tuple"):
        await DelegateFoldExecutor().node_execute(
            _ctx(),
            NodeInput(
                port_values={
                    "delegation_receipt": [_receipt(delegate_from="a")],
                }
            ),
        )


# ---------------------------------------------------------------------------
# Idempotency + determinism (C9 / C8 invariants)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fold_is_idempotent() -> None:
    receipts = (
        _receipt(delegate_from="agent.a", payload={"answer": 1}),
        _receipt(delegate_from="agent.b", status="error", error="oops"),
    )
    out1 = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": receipts}),
    )
    out2 = await DelegateFoldExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"delegation_receipt": receipts}),
    )
    # ``Decision.created_at`` is wall-clock populated, so we compare on the
    # fold-derived fields only. ``FoldedDelegationResult`` is frozen and
    # wholly derived from inputs, so equality is exact.
    assert out1.port_values["folded_result"] == out2.port_values["folded_result"]
    d1: Decision = out1.port_values["decision"]
    d2: Decision = out2.port_values["decision"]
    assert d1.decision_id == d2.decision_id
    assert d1.action_type == d2.action_type
    assert d1.rationale == d2.rationale
    assert d1.confidence == d2.confidence
    assert d1.extra == d2.extra


@pytest.mark.asyncio
async def test_fold_is_pure_across_instances() -> None:
    """Two freshly-constructed executors must agree on the same input."""
    receipts = (_receipt(delegate_from="agent.a", payload={"x": 1}),)
    node_input = NodeInput(port_values={"delegation_receipt": receipts})
    out_a = await DelegateFoldExecutor().node_execute(_ctx(), node_input)
    out_b = await DelegateFoldExecutor().node_execute(_ctx(), node_input)
    assert out_a.port_values["folded_result"] == out_b.port_values["folded_result"]
    d_a: Decision = out_a.port_values["decision"]
    d_b: Decision = out_b.port_values["decision"]
    assert d_a.decision_id == d_b.decision_id
    assert d_a.action_type == d_b.action_type
    assert d_a.rationale == d_b.rationale
    assert d_a.confidence == d_b.confidence


# ---------------------------------------------------------------------------
# Compositional sanity: declared port schema is the typed contract
# ---------------------------------------------------------------------------


def test_declared_io_schema_matches_task_spec() -> None:
    executor = DelegateFoldExecutor()
    assert executor.semantic_name == "delegate.fold"
    assert executor.region == "delegate"
    assert executor.declared_inputs == ("delegation_receipt",)
    assert executor.declared_outputs == ("decision", "folded_result")


def test_setup_provides_composite_key() -> None:
    """The plugin id stays ``phase.delegate.fold`` for cordis discovery."""
    executor = DelegateFoldExecutor()
    assert f"{executor.region}::{executor.semantic_name}" == "delegate::delegate.fold"
