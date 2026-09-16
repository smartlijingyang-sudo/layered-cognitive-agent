"""act.observe normalize (PR-3.8.7 fold from ``act.result.normalize``).

Per `docs/superpowers/plans/2026-09-15-pr3.8.7-act-observe-normalize-merge.md` §Task 1,
``act.observe`` carries the schema/spill/coerce/error_reason normalization steps
in-place inside ``node_execute``. The typed-boundary port schema is unchanged
(``declared_inputs=("receipt",)``, ``declared_outputs=("receipt",)``); the
normalize logic is invisible to the port schema per AGENTS.md §3 C13.

Idempotency + determinism: same input receipt produces a structurally equivalent
``EffectReceipt`` regardless of how many times ``node_execute`` is called.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
)
from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.act.observe.observe import (
    _MAX_OUTPUT_REF_BYTES,
    ActObserveExecutor,
    _normalize_receipt,
)


def _make_context() -> NodeContext:
    return NodeContext(runtime={}, budget={}, metadata={"plan_ref": "test"})


def _succeeded_receipt() -> EffectReceipt:
    return EffectReceipt(
        invocation_id="inv_well_formed",
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key="idem_well_formed",
        provider="body.act",
    )


@pytest.mark.asyncio
async def test_observe_passes_through_well_formed_receipt() -> None:
    """Well-formed receipt — normalize is no-op; same instance, no spill, no error_reason rewrite."""
    receipt = _succeeded_receipt()
    executor = ActObserveExecutor()

    output = await executor.node_execute(_make_context(), NodeInput({"receipt": receipt}))

    normalized = output.port_values["receipt"]
    assert normalized is receipt
    assert normalized.output_ref is None
    assert normalized.error_code is None
    assert normalized.failure_kind is None
    # PR-3: ``should_terminate`` no longer produced by the normalize node.
    # Routing decision lives on the sibling ``act.observe.terminate_decide``
    # node; see ``tests/act/test_observe_terminate_decide.py``.
    assert "should_terminate" not in output.port_values


@pytest.mark.asyncio
async def test_observe_spills_oversized_output_ref() -> None:
    """``output_ref`` exceeding ADR-0197 ``guard.tool-result-spill`` threshold → spill URI."""
    oversized_ref = "x" * (_MAX_OUTPUT_REF_BYTES + 1)
    receipt = EffectReceipt(
        invocation_id="inv_oversized",
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key="idem_oversized",
        provider="body.act",
        output_ref=oversized_ref,
    )
    executor = ActObserveExecutor()

    output = await executor.node_execute(_make_context(), NodeInput({"receipt": receipt}))

    normalized = output.port_values["receipt"]
    assert normalized.output_ref is not None
    assert normalized.output_ref.startswith("spill://")
    assert normalized.output_ref.endswith("inv_oversized")
    # Spilled stub must be small enough to be safe for downstream typed inference.
    assert len(normalized.output_ref.encode("utf-8")) <= _MAX_OUTPUT_REF_BYTES


@pytest.mark.asyncio
async def test_observe_populates_error_reason_from_closed_set() -> None:
    """``failure_kind`` set + ``error_code`` cleared → closed-set map populates ``error_code``.

    Deterministic + no exception: same ``failure_kind`` produces same ``error_reason``.
    Unknown ``failure_kind`` is ignored (no error_code rewrite, no exception).

    The ``FAILED outcome + error_code=None`` state is not directly constructible
    via ``EffectReceipt(...)`` (``__post_init__`` rejects it), so we construct a
    valid receipt and bypass the frozen + invariant check via ``object.__setattr__``
    to model the state a downstream unclassified caller might produce.
    """
    receipt = EffectReceipt(
        invocation_id="inv_exec",
        outcome=EffectOutcome.FAILED,
        idempotency_key="idem_exec",
        provider="body.act",
        error_code="tool_failed",
        failure_kind=FAILURE_KIND_EXECUTION,
    )
    # Test-only bypass: simulate the state where body has classified failure_kind
    # but the error_code slot was not populated (a state EffectReceipt's
    # __post_init__ rejects from direct construction).
    object.__setattr__(receipt, "error_code", None)
    assert receipt.error_code is None

    executor = ActObserveExecutor()
    output = await executor.node_execute(_make_context(), NodeInput({"receipt": receipt}))

    normalized = output.port_values["receipt"]
    # Closed-set map (failure_kind → error_reason) is identity for known failure_kinds.
    assert normalized.error_code == FAILURE_KIND_EXECUTION
    assert normalized.failure_kind == FAILURE_KIND_EXECUTION
    # PR-3: the normalize node is pure receipt rewrite; the deterministic-
    # failure shortcut (should_terminate) is now produced by
    # ``act.observe.terminate_decide`` and asserted in
    # ``tests/act/test_observe_terminate_decide.py``.
    assert "should_terminate" not in output.port_values


@pytest.mark.asyncio
async def test_observe_normalize_is_idempotent() -> None:
    """Idempotency — same input twice produces structurally equivalent normalized receipts.

    The input exercises both normalize paths in one receipt: ``output_ref`` > 50_000 bytes
    (spill) and ``failure_kind`` set with ``error_code`` unset (closed-set populate).
    """
    receipt = EffectReceipt(
        invocation_id="inv_idem",
        outcome=EffectOutcome.FAILED,
        idempotency_key="idem_idem",
        provider="body.act",
        error_code="transient",
        failure_kind=FAILURE_KIND_TRANSIENT,
        output_ref="y" * (_MAX_OUTPUT_REF_BYTES + 1),
    )
    # Bypass to model the unclassified state for the closed-set populate branch.
    object.__setattr__(receipt, "error_code", None)

    executor = ActObserveExecutor()

    first_output = await executor.node_execute(_make_context(), NodeInput({"receipt": receipt}))
    first_normalized = first_output.port_values["receipt"]

    second_output = await executor.node_execute(_make_context(), NodeInput({"receipt": receipt}))
    second_normalized = second_output.port_values["receipt"]

    # Structurally equivalent (all fields equal); instances may differ.
    assert first_normalized == second_normalized

    # Re-applying the normalize step to the first normalized receipt yields
    # the same struct again — no further mutation beyond idempotent.
    third_normalized = _normalize_receipt(first_normalized)
    assert third_normalized == first_normalized
