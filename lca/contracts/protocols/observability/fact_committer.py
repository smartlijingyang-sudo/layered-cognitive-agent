"""FactCommitter — unified declarative fact commit seam (ADR-0192).

Harness and runtime commit RunFacts, evidence, and effect observations through
this protocol. Implementations route to ``Session.append`` and authorized spine
EPs; they must not expose Journal/RunStore as a parallel production API.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.protocols.act.command.envelope import RunFact


@runtime_checkable
class FactCommitter(Protocol):
    """Single commit boundary for declarative run facts."""

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str: ...

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str: ...

    def commit_observation(self, observation: object, *, plan_ref: str, node_ref: str) -> str: ...


__all__ = ["FactCommitter"]
