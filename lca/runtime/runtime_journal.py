"""Runtime journal adapter for declarative Turn execution.

The generic interpreter depends only on ``JournalCommitter``.  Runtime result
finalization additionally needs the last committed sequence, so this module
makes that narrow runtime-level contract explicit and supplies the production
observability adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from lca.contracts.protocols.act.command_envelope import RunFact
from lca.contracts.protocols.declarative.declarative_phase_graph import JournalCommitter
from lca.infrastructure.observability import record_runtime


@runtime_checkable
class RuntimeJournal(JournalCommitter, Protocol):
    """A Turn journal that also exposes its monotonic committed sequence."""

    @property
    def sequence(self) -> int: ...


class RuntimeJournalCommitter(RuntimeJournal):
    """Publish declarative facts to runtime observability with stable sequencing."""

    def __init__(self) -> None:
        self._sequence = 0

    @property
    def sequence(self) -> int:
        """Return the number of facts, evidence records, and receipts committed this Turn."""

        return self._sequence

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str:
        return self._record(
            operation="phase.fact",
            source=node_ref,
            plan_ref=plan_ref,
            attributes={"fact_id": fact.fact_id, "kind": fact.kind, "payload": dict(fact.payload)},
        )

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        return self._record(
            operation="phase.evidence",
            source=node_ref,
            plan_ref=plan_ref,
            attributes={"evidence_ref": evidence_ref},
        )

    def commit_observation(self, observation: object, *, plan_ref: str, node_ref: str) -> str:
        return self._record(
            operation="effect.receipt",
            source=node_ref,
            plan_ref=plan_ref,
            attributes={"observation_type": type(observation).__name__, "observation": observation},
        )

    def _record(
        self,
        *,
        operation: str,
        source: str,
        plan_ref: str,
        attributes: Mapping[str, object],
    ) -> str:
        self._sequence += 1
        stamped = record_runtime(
            "journal",
            operation,
            plugin=source,
            attributes={"plan_ref": plan_ref, **dict(attributes)},
        )
        event_id = getattr(stamped, "event_id", "") if stamped is not None else ""
        return event_id or f"{plan_ref}:{source}:{operation}:{self._sequence}"


__all__ = ["RuntimeJournal", "RuntimeJournalCommitter"]
