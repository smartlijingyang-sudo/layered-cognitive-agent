"""Restricted data exposed to one declarative phase and its contributions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.act.command_envelope import RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_execution import (
    JournalCommitter,
    PhaseCapabilityReader,
    PhaseContext,
)


@dataclass(slots=True)
class RestrictedPhaseContext(PhaseContext):
    """A narrow per-phase view that prevents discovery of undeclared services.

    Phase implementations can emit Journal facts and propose reducer deltas, but
    they do not receive a live runtime scope or mutable AgentState owner.
    """

    plan_ref: str
    node_ref: str
    state: AgentState
    journal: JournalCommitter
    budget: Budget
    artifacts: Mapping[str, object]
    capabilities: PhaseCapabilityReader
    decision: Decision | None = None
    observation: Observation | None = None
    reflection: Reflection | None = None
    checkpoint_reason: str | None = None
    _proposed_deltas: list[RunDelta] = field(default_factory=list)

    def emit_fact(self, fact: RunFact) -> str:
        return str(self.journal.commit_fact(fact, plan_ref=self.plan_ref, node_ref=self.node_ref))

    def propose_delta(self, delta: RunDelta) -> None:
        self._proposed_deltas.append(delta)

    @property
    def proposed_deltas(self) -> tuple[RunDelta, ...]:
        return tuple(self._proposed_deltas)


__all__ = ["RestrictedPhaseContext"]
