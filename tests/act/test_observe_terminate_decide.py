"""act.observe.terminate_decide — typed should_terminate decision node (PR-3).

Per `docs/superpowers/plans/2026-09-16-act-subgraph-tightening.md` PR-3 and
Agent Note `docs/notes/proposed/contract/2026-09-16-act-observe-normalize-split.md`:

``act.observe.terminate_decide`` consumes the normalized ``receipt`` port and
emits two ports:

- ``receipt`` — passthrough (the downstream nodes consume the same receipt)
- ``should_terminate`` — bool routing decision

Decision rule (AGENTS.md §2.2 routing-decision closed-set):

    should_terminate = receipt.failure_kind is None and receipt.outcome.value == "failed"

Only an unclassified failure terminates: that receipt shape is what
``concept.effect.execute`` produces when the gateway itself raised, i.e. the
host never dispatched the effect. A classified tag means a tool ran and
reported on its own subject, which the model has to see.

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
    """``failure_kind == execution`` → should_terminate=False.

    A classified tool failure is the tool's report about its own subject, so
    the model must see it and pick another approach
    (docs/specs/tool-failure-recovery.md §3 「可以更换方案或工具」, §7
    「USE_TOOL + failed Observation → 通常继续」). Only an *unclassified*
    failure — the host could not dispatch the effect at all — terminates.
    """
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

    assert out.port_values["should_terminate"] is False
    assert out.port_values["receipt"] is receipt


@pytest.mark.asyncio
async def test_sandbox_command_failure_returns_to_model() -> None:
    """Regression for run_eed09c1df112: a failing sandbox command must not end the run.

    Step 4 of that run issued ``runCommand`` + ``executeCode``; both came back
    ``ModuleNotFoundError`` (pdf2image / pdfplumber absent from the sandbox
    image). The adapter tagged them ``failure_kind="execution"``, this node
    emitted ``should_terminate=True``, and the run reached ``terminal.commit``
    with ``kernel.run.stop outcome=failure`` — the model never got the turn it
    needed to install the package or switch to ``pdftotext``. Same shape killed
    run_aebabe6c1056 (``exit code 1``) and run_6d3aeff0b339 (FileNotFoundError).
    """
    from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor

    receipt = EffectReceipt(
        invocation_id="toolu_023deb82180b43e4ab9adf33",
        outcome=EffectOutcome.FAILED,
        idempotency_key="sha256:3563e0320b4647b1:act.dispatch:decision_de1c7d99a59a",
        provider="body.act",
        error_code="ModuleNotFoundError: No module named 'pdf2image'",
        failure_kind=FAILURE_KIND_EXECUTION,
    )

    out = await ActObserveTerminateDecideExecutor().node_execute(
        _make_context(),
        NodeInput(port_values={"receipt": receipt}),
    )

    assert out.port_values["should_terminate"] is False


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
    """Unclassified failure (failure_kind=None but outcome=failed) → should_terminate=True.

    No classifier tag means no tool ever reported anything: the host failed to
    dispatch the effect (``concept.effect.execute`` catches the gateway
    exception and builds exactly this receipt). Continuing the loop would ask
    the model to reason about a side effect whose state is unknown, so this is
    the one shape that routes to terminal.commit.
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
