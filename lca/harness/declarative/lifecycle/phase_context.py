"""Restricted data exposed to one declarative phase and its contributions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.act.command.envelope import RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    JournalCommitter,
    PhaseCapabilityReader,
    PhaseContext,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    SemanticPhase,
)


@dataclass(slots=True)
class RestrictedPhaseContext(PhaseContext):
    """A narrow per-phase view that prevents discovery of undeclared services.

    Phase implementations can emit Journal facts and propose reducer deltas, but
    they do not receive a live runtime scope or mutable AgentState owner.

    Per ADR-0219 §4: cross-node product propagation goes via
    ``results_by_phase: Mapping[SemanticPhase, PhaseResult]`` + the
    ``payload_of(phase, want)`` accessor. The legacy string-keyed
    ``artifacts`` dict plus the ``decision`` / ``observation`` / ``reflection``
    single fields have been removed.
    """

    plan_ref: str
    node_ref: str
    state: AgentState
    journal: JournalCommitter
    budget: Budget
    capabilities: PhaseCapabilityReader
    results_by_phase: Mapping[SemanticPhase, PhaseResult] = field(default_factory=dict)
    checkpoint_reason: str | None = None
    _proposed_deltas: list[RunDelta] = field(default_factory=list)

    def emit_fact(self, fact: RunFact) -> str:
        return str(self.journal.commit_fact(fact, plan_ref=self.plan_ref, node_ref=self.node_ref))

    def propose_delta(self, delta: RunDelta) -> None:
        self._proposed_deltas.append(delta)

    @property
    def proposed_deltas(self) -> tuple[RunDelta, ...]:
        return tuple(self._proposed_deltas)

    def payload_of(
        self,
        phase: SemanticPhase,
        want: type[object],
    ) -> object | None:
        """Return the typed payload from one upstream phase result.

        Single typed entry (ADR-0219 §4.3). Reads
        ``self.results_by_phase[phase].payload`` and returns it if it is
        an instance of ``want``, else ``None``. The data flow is visible
        at the call site.
        """
        phase_result = self.results_by_phase.get(phase)
        if phase_result is None:
            return None
        payload = phase_result.payload
        return payload if isinstance(payload, want) else None


__all__ = ["RestrictedPhaseContext"]