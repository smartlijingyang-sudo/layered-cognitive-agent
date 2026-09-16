"""act.observe.commit_fact — typed RunFact journal commit node (PR-3 NEW Task 3.2.7a).

Per `docs/superpowers/plans/2026-09-16-act-subgraph-tightening.md` PR-3
NEW Task 3.2.7a (L-1 / 「act 业务不知道图存在」boundary fix):

``act.observe.commit_fact`` consumes the normalized ``receipt`` port,
constructs a typed ``RunFact(kind="effect.observed", payload={...})``,
and calls ``journal.commit_fact(fact, plan_ref, node_ref)`` once. The
``receipt`` is passed through unchanged on the ``receipt`` port.

ADR-0235 / PR-5 R-3 follow-through: ``journal_capability`` is injected by
the kernel as a typed Contract at construction (fail-loud if absent).
The node no longer reads ``context.runtime.journal`` via ``getattr(...,
None)`` silent-skip. Tests inject the capability directly at
construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.protocols.act.command.envelope import RunFact
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)


@dataclass
class FakeJournal:
    """In-memory journal stand-in for tests.

    Mirrors the contract surface ``act.observe.commit_fact`` relies on:
    ``commit_fact(fact, plan_ref=..., node_ref=...)``. Records every call
    so tests can assert side-effects deterministically.
    """

    committed: list[RunFact] = field(default_factory=list)
    last_plan_ref: str = ""
    last_node_ref: str = ""

    def commit_fact(
        self,
        fact: RunFact,
        *,
        plan_ref: str,
        node_ref: str,
    ) -> None:
        self.committed.append(fact)
        self.last_plan_ref = plan_ref
        self.last_node_ref = node_ref


@pytest.mark.asyncio
async def test_commit_fact_runs_observed_kind() -> None:
    """Single receipt in → exactly one ``effect.observed`` RunFact committed."""
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key="k",
        provider="p",
    )
    journal = FakeJournal()
    node = ActObserveCommitFactExecutor(journal_capability=journal)

    out = await node.node_execute(
        NodeContext(
            runtime={},
            budget={},
            metadata={"plan_ref": "plan-xyz", "node_id": "act.observe.commit_fact"},
        ),
        NodeInput(port_values={"receipt": receipt}),
    )

    assert out.port_values["receipt"] is receipt
    assert len(journal.committed) == 1
    assert journal.committed[0].kind == "effect.observed"
    assert journal.committed[0].plan_ref == "plan-xyz"
    assert journal.last_node_ref == "act.observe.commit_fact"


@pytest.mark.asyncio
async def test_commit_fact_payload_includes_receipt_fields() -> None:
    """RunFact payload carries receipt classifier fields (invocation_id, outcome,
    provider, idempotency_key, error_code) so reflect / remember nodes can do
    typed inference on the journal fact without re-reading the receipt.
    """
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    receipt = EffectReceipt(
        invocation_id="inv_payload_test",
        outcome=EffectOutcome.FAILED,
        idempotency_key="idem_payload",
        provider="body.act",
        error_code="timeout",
    )
    journal = FakeJournal()
    node = ActObserveCommitFactExecutor(journal_capability=journal)

    await node.node_execute(
        NodeContext(
            runtime={},
            budget={},
            metadata={"plan_ref": "plan-payload", "node_id": "act.observe.commit_fact"},
        ),
        NodeInput(port_values={"receipt": receipt}),
    )

    fact = journal.committed[0]
    payload = fact.payload
    assert payload["invocation_id"] == "inv_payload_test"
    assert payload["outcome"] == "failed"
    assert payload["provider"] == "body.act"
    assert payload["idempotency_key"] == "idem_payload"
    assert payload["error_code"] == "timeout"


@pytest.mark.asyncio
async def test_commit_fact_fact_id_format() -> None:
    """``fact_id`` is deterministic: ``f"{plan_ref}:{node_id}:{invocation_id}"``."""
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    receipt = EffectReceipt(
        invocation_id="inv_fid",
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key="k",
        provider="p",
    )
    journal = FakeJournal()
    node = ActObserveCommitFactExecutor(journal_capability=journal)

    await node.node_execute(
        NodeContext(
            runtime={},
            budget={},
            metadata={"plan_ref": "plan-1", "node_id": "act.observe.commit_fact"},
        ),
        NodeInput(port_values={"receipt": receipt}),
    )

    assert journal.committed[0].fact_id == "plan-1:act.observe.commit_fact:inv_fid"


@pytest.mark.asyncio
async def test_commit_fact_rejects_non_receipt_input() -> None:
    """Non-receipt input → TypeError (typed-port boundary contract)."""
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    journal = FakeJournal()
    node = ActObserveCommitFactExecutor(journal_capability=journal)
    with pytest.raises(TypeError):
        await node.node_execute(
            NodeContext(
                runtime={},
                budget={},
                metadata={"plan_ref": "plan", "node_id": "act.observe.commit_fact"},
            ),
            NodeInput(port_values={"receipt": "not a receipt"}),
        )
    assert journal.committed == []


@pytest.mark.asyncio
async def test_commit_fact_missing_journal_capability_fails_loud() -> None:
    """ADR-0235 / PR-5 R-3 follow-through: missing ``journal_capability`` now
    raises ``RuntimeError`` (typed-contract fail-loud). The previous silent
    skip (``getattr(..., None)``) closed the observation-plane write
    silently and was a R-3 boundary violation.
    """
    from lca.nodes.act.observe.commit_fact import ActObserveCommitFactExecutor

    receipt = EffectReceipt(
        invocation_id=new_id("inv"),
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key="k",
        provider="p",
    )
    node = ActObserveCommitFactExecutor()  # no journal_capability injected

    with pytest.raises(RuntimeError, match="journal_capability"):
        await node.node_execute(
            NodeContext(
                runtime={},
                budget={},
                metadata={"plan_ref": "plan", "node_id": "act.observe.commit_fact"},
            ),
            NodeInput(port_values={"receipt": receipt}),
        )
