"""Pin act.observe.terminate_decide deterministic-failure shortcut behavior.

Locks in the post-retirement (plan
`docs/plans/2026-09-14-stop-decision-retirement.md`, PR-3) contract:
when `EffectReceipt.failure_kind == "execution"`, the act subgraph
emits `should_terminate=True` so the outer driver routes the next edge
to `terminal.commit` instead of looping back to `think.main`. This
replaces the retired `DefaultStopPolicy._deterministic_failure_stop`
shortcut.

PR-3 split: the decision was previously produced by the `act.observe`
node; it now lives on the dedicated `act.observe.terminate_decide` node
that sits between `act.observe.commit_fact` and `reflect.main` /
`terminal.commit` in the act subgraph wiring. This file targets the
new node (the same typed-port contract — `receipt` in, `receipt` +
`should_terminate` out).
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
from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor


def _make_context() -> NodeContext:
    return NodeContext(runtime={}, budget={}, metadata={"plan_ref": "test"})


def _receipt(*, failure_kind: str | None) -> EffectReceipt:
    outcome = EffectOutcome.FAILED if failure_kind else EffectOutcome.SUCCEEDED
    error_code = "tool_failed" if failure_kind else None
    return EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=outcome,
        idempotency_key="idem_test",
        provider="body.act",
        error_code=error_code,
        failure_kind=failure_kind,
    )


@pytest.mark.asyncio
async def test_act_observe_emits_should_terminate_on_execution_failure() -> None:
    executor = ActObserveTerminateDecideExecutor()
    receipt = _receipt(failure_kind=FAILURE_KIND_EXECUTION)

    output = await executor.node_execute(_make_context(), NodeInput({"receipt": receipt}))

    assert output.port_values["should_terminate"] is True
    assert output.port_values["receipt"] is receipt


@pytest.mark.asyncio
async def test_act_observe_does_not_terminate_on_transient_failure() -> None:
    executor = ActObserveTerminateDecideExecutor()
    receipt = _receipt(failure_kind=FAILURE_KIND_TRANSIENT)

    output = await executor.node_execute(_make_context(), NodeInput({"receipt": receipt}))

    assert output.port_values["should_terminate"] is False


@pytest.mark.asyncio
async def test_act_observe_does_not_terminate_on_success() -> None:
    executor = ActObserveTerminateDecideExecutor()
    receipt = _receipt(failure_kind=None)

    output = await executor.node_execute(_make_context(), NodeInput({"receipt": receipt}))

    assert output.port_values["should_terminate"] is False


@pytest.mark.asyncio
async def test_act_observe_emits_should_terminate_on_legacy_failed_receipt() -> None:
    """Pre-classifier failure (failure_kind=None but outcome=failed).

    Mirrors the historical `run_0d71855ae274` regression class: the
    receipt has no classifier tag (Body pre-classifier code path) but
    the error_code is non-empty. The terminator still routes to
    terminal.commit so the loop never cycles the same tool call.
    """
    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.FAILED,
        idempotency_key="idem_legacy",
        provider="body.act",
        error_code="no_such_file",
    )
    assert receipt.failure_kind is None

    output = await ActObserveTerminateDecideExecutor().node_execute(
        _make_context(), NodeInput({"receipt": receipt})
    )

    assert output.port_values["should_terminate"] is True


@pytest.mark.asyncio
async def test_act_observe_rejects_non_receipt_input() -> None:
    executor = ActObserveTerminateDecideExecutor()
    with pytest.raises(TypeError):
        await executor.node_execute(_make_context(), NodeInput({"receipt": "not a receipt"}))
