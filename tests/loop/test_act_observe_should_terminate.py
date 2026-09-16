"""Pin act.observe.terminate_decide routing behavior.

Locks in the post-retirement (plan
`docs/plans/2026-09-14-stop-decision-retirement.md`, PR-3) contract:
only an *unclassified* failed receipt — the host never got the effect
out of the door — emits `should_terminate=True` and routes the outer
edge to `terminal.commit`. Every classified failure (`execution`,
`transient`, `validation`, `tool_wire`) loops back to `think.main` so
the model sees the tool's report, per
`docs/specs/tool-failure-recovery.md` §3/§6.1/§7.

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
async def test_act_observe_does_not_terminate_on_execution_failure() -> None:
    """A classified tool failure goes back to the model, not to terminal.commit.

    ``execution`` means "retrying the same args is pointless", not "the run
    cannot continue" — SafeExecutor already refuses the infra-level retry, and
    docs/specs/tool-failure-recovery.md §3 keeps the cognitive retry (换方案或
    换工具) open. Terminating here is what ended run_eed09c1df112 after its
    sandbox reported ``ModuleNotFoundError``, before the model could react.
    """
    executor = ActObserveTerminateDecideExecutor()
    receipt = _receipt(failure_kind=FAILURE_KIND_EXECUTION)

    output = await executor.node_execute(_make_context(), NodeInput({"receipt": receipt}))

    assert output.port_values["should_terminate"] is False
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
    """Unclassified failure (failure_kind=None but outcome=failed).

    No classifier tag means no tool reported anything: the host failed
    to dispatch the effect at all. The run terminates rather than ask
    the model to reason about a side effect whose state is unknown.
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
