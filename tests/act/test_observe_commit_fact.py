"""act.observe.commit_fact — receipt passthrough (PR-3 close-out).

PR-3 close-out: the original ``commit_fact`` node also wrote a
``RunFact(kind="effect.observed", ...)`` to a journal capability, which
created a parallel commit path that violated AGENTS.md §2.2 (fact /
status / decision single-responsibility) and ADR-0192 (FactCommitter
routes through Session.append as the SSOT). The node now does one job:
``EffectReceipt`` → ``EffectReceipt`` passthrough. RunFact construction
and journal commit move to ``reducer.fold`` via ``FactCommitter``
(ADR-0192 E0/E2, ADR-0194 P1-08).

These tests assert the new contract:

1. ``receipt in → receipt out`` identity (no journal, no RunFact).
2. Non-receipt input → ``TypeError`` (typed-port boundary fail-loud).
3. ``requires=()`` so the plugin attaches without any journal_capability /
   journal_backends producer wired into the resolved profile.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)


def _make_receipt(
    *,
    invocation_id: str | None = None,
    outcome: EffectOutcome = EffectOutcome.SUCCEEDED,
    provider: str = "p",
    error_code: str = "",
) -> EffectReceipt:
    return EffectReceipt(
        invocation_id=invocation_id or new_id("inv"),
        outcome=outcome,
        idempotency_key="k",
        provider=provider,
        error_code=error_code,
    )


@pytest.mark.asyncio
async def test_commit_fact_passes_receipt_through() -> None:
    """Single receipt in → same receipt out, no journal side-effects."""
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    receipt = _make_receipt()
    node = ActObserveCommitFactExecutor()

    out = await node.node_execute(
        NodeContext(runtime={}, budget={}, metadata={}),
        NodeInput(port_values={"receipt": receipt}),
    )

    assert out.port_values == {"receipt": receipt}
    # No journal / no RunFact — the node has no side-effects.
    assert "journal" not in out.port_values
    assert "fact" not in out.port_values


@pytest.mark.asyncio
async def test_commit_fact_rejects_non_receipt_input() -> None:
    """Non-receipt input → ``TypeError`` (typed-port boundary contract)."""
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    node = ActObserveCommitFactExecutor()
    with pytest.raises(TypeError, match="EffectReceipt"):
        await node.node_execute(
            NodeContext(runtime={}, budget={}, metadata={}),
            NodeInput(port_values={"receipt": "not a receipt"}),
        )


@pytest.mark.asyncio
async def test_commit_fact_rejects_missing_port() -> None:
    """Missing ``receipt`` port → ``TypeError`` (no silent skip)."""
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    node = ActObserveCommitFactExecutor()
    with pytest.raises(TypeError, match="EffectReceipt"):
        await node.node_execute(
            NodeContext(runtime={}, budget={}, metadata={}),
            NodeInput(port_values={}),
        )


@pytest.mark.asyncio
async def test_commit_fact_preserves_receipt_on_failed_outcome() -> None:
    """Failed receipts (timeout, denied, etc.) still pass through unchanged."""
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    receipt = _make_receipt(
        outcome=EffectOutcome.FAILED,
        provider="body.act",
        error_code="timeout",
    )
    node = ActObserveCommitFactExecutor()

    out = await node.node_execute(
        NodeContext(runtime={}, budget={}, metadata={}),
        NodeInput(port_values={"receipt": receipt}),
    )

    assert out.port_values["receipt"] is receipt
    assert out.port_values["receipt"].error_code == "timeout"


def test_commit_fact_plugin_declares_no_requires() -> None:
    """Plugin-level capability graph: ``commit_fact`` must not depend on any
    journal / ``JournalCapability`` / ``journal_backends`` capability — RunFact
    commit lives in the reducer fold (ADR-0192 SSOT), not the act subgraph.
    """
    from lca.nodes.act.observe.commit_fact import setup

    # ``setup`` is the @plugin(...)-decorated Plugin carrier; its
    # ``_lca_definition`` is the immutable PluginDefinition (required_/
    # provided_capability_keys / layer / effects are all declared there).
    definition = setup._lca_definition
    assert definition.required_capability_keys == ()
    assert definition.provided_capability_keys == ("act::act.observe.commit_fact",)


def test_commit_fact_executor_has_no_capability_field() -> None:
    """``ActObserveCommitFactExecutor`` carries no ``journal_capability`` slot.

    This pins the post-close-out shape so a future PR cannot re-introduce
    the parallel commit mechanism by silently adding the field back.
    """
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    executor = ActObserveCommitFactExecutor()
    forbidden = {
        "journal_capability",
        "journal_backend",
        "backend",
        "fact_committer",
        "session",
    }
    leaked = forbidden & set(executor.__dataclass_fields__)  # type: ignore[attr-defined]
    assert leaked == set(), (
        f"commit_fact must stay pure-transform; found forbidden fields {leaked}"
    )