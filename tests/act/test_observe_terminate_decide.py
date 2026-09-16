"""act.observe.terminate_decide — typed should_terminate decision node (PR-3).

Per `docs/superpowers/plans/2026-09-16-act-subgraph-tightening.md` PR-3 and
Agent Note `docs/notes/proposed/contract/2026-09-16-act-observe-normalize-split.md`:

``act.observe.terminate_decide`` consumes the normalized ``receipt`` port and
emits two ports:

- ``receipt`` — passthrough (the downstream nodes consume the same receipt)
- ``should_terminate`` — bool routing decision

Decision rule (lifted verbatim from the retired act.observe block, AGENTS.md
§2.2 routing-decision closed-set):

    should_terminate = (
        receipt.failure_kind == FAILURE_KIND_EXECUTION
        or (receipt.failure_kind is None and receipt.outcome.value == "failed")
    )

The node is pure: no journal writes, no Body dispatch, no capability reads.
It is the typed-port D4 boundary for the ``should_terminate`` decision so
``act.observe`` no longer has to mix receipt-normalize + decision + commit_fact
in a single node.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
)
from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)


def _make_context() -> NodeContext:
    return NodeContext(runtime={}, budget={}, metadata={"plan_ref": "test"})


@pytest.mark.asyncio
async def test_terminate_decide_on_execution_failure_kind() -> None:
    """``failure_kind == execution`` → should_terminate=True (deterministic failure)."""
    from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor

    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.FAILED,
        idempotency_key="k",
        provider="p",
        error_code="tool_failed",
        failure_kind=FAILURE_KIND_EXECUTION,
    )
    node = ActObserveTerminateDecideExecutor()

    out = await node.node_execute(
        _make_context(),
        NodeInput(port_values={"receipt": receipt}),
    )

    assert out.port_values["should_terminate"] is True
    assert out.port_values["receipt"] is receipt


@pytest.mark.asyncio
async def test_terminate_decide_on_success_no_failure_kind() -> None:
    """Successful receipt → should_terminate=False."""
    from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor

    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key="k",
        provider="p",
    )
    node = ActObserveTerminateDecideExecutor()

    out = await node.node_execute(
        _make_context(),
        NodeInput(port_values={"receipt": receipt}),
    )

    assert out.port_values["should_terminate"] is False
    assert out.port_values["receipt"] is receipt


@pytest.mark.asyncio
async def test_terminate_decide_on_transient_failure_kind() -> None:
    """``failure_kind == transient`` → should_terminate=False (retryable)."""
    from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor

    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.FAILED,
        idempotency_key="k",
        provider="p",
        error_code="timeout",
        failure_kind=FAILURE_KIND_TRANSIENT,
    )
    node = ActObserveTerminateDecideExecutor()

    out = await node.node_execute(
        _make_context(),
        NodeInput(port_values={"receipt": receipt}),
    )

    assert out.port_values["should_terminate"] is False


@pytest.mark.asyncio
async def test_terminate_decide_on_legacy_failed_receipt() -> None:
    """Pre-classifier failure (failure_kind=None but outcome=failed) → should_terminate=True.

    Mirrors the historical ``run_0d71855ae274`` regression class: the receipt
    has no classifier tag (Body pre-classifier code path) but the error_code
    is non-empty. The terminator still routes to terminal.commit so the loop
    never cycles the same tool call.
    """
    from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor

    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.FAILED,
        idempotency_key="k",
        provider="p",
        error_code="no_such_file",
    )
    assert receipt.failure_kind is None
    node = ActObserveTerminateDecideExecutor()

    out = await node.node_execute(
        _make_context(),
        NodeInput(port_values={"receipt": receipt}),
    )

    assert out.port_values["should_terminate"] is True


@pytest.mark.asyncio
async def test_terminate_decide_rejects_non_receipt_input() -> None:
    """Non-receipt input → TypeError (typed-port boundary contract)."""
    from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor

    node = ActObserveTerminateDecideExecutor()
    with pytest.raises(TypeError):
        await node.node_execute(
            _make_context(),
            NodeInput(port_values={"receipt": "not a receipt"}),
        )


@pytest.mark.asyncio
async def test_terminate_decide_missing_receipt_port() -> None:
    """Missing receipt port → TypeError."""
    from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor

    node = ActObserveTerminateDecideExecutor()
    with pytest.raises(TypeError):
        await node.node_execute(
            _make_context(),
            NodeInput(port_values={}),
        )
