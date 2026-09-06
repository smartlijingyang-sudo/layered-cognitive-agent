"""Legacy PerceiveHub state.extra adapter (COMPAT — ADR-0191).

# COMPAT(owner: ADR-0191, from: state.extra gate_decided/current_manifest bucket,
# to: Session.append gate.decided.v1 / context.manifested.v1 + AgentState.perceive,
# delete_when: rg 'record_event_to_state|LEGACY_GATE_DECIDED' lca/ tests/ = 0 only in
# this module && PerceiveState.gate_decided unused,
# forbidden_new_usage: new gate/perceive paths writing gate_decided bucket)

Production paths now emit durable Session facts and fold via
``lca.contracts.harness.fold.perceive``. ``AgentState.perceive`` is the
Reducer-owned manifest projection. This module remains for tests that
still seed legacy ``state.extra`` slots directly.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState

LEGACY_GATE_DECIDED_KEY = "gate_decided"
LEGACY_CURRENT_MANIFEST_KEY = "current_manifest"


@dataclass
class PerceiveState:
    """Typed view over legacy perception slots in ``state.extra``."""

    current_manifest: ContextManifest | None = None
    gate_decided: list[GateDecided] = field(default_factory=list)

    @classmethod
    def from_agent_state(cls, state: AgentState) -> PerceiveState:
        manifest = state.extra.get(LEGACY_CURRENT_MANIFEST_KEY)
        bucket = state.extra.get(LEGACY_GATE_DECIDED_KEY) or []
        if not isinstance(bucket, list):
            bucket = []
        normalized: list[GateDecided] = [item for item in bucket if isinstance(item, GateDecided)]
        return cls(
            current_manifest=manifest if isinstance(manifest, ContextManifest) else None,
            gate_decided=normalized,
        )

    def commit(self, state: AgentState) -> None:
        state.extra[LEGACY_CURRENT_MANIFEST_KEY] = self.current_manifest
        state.extra[LEGACY_GATE_DECIDED_KEY] = list(self.gate_decided)


def record_event_to_state(state: AgentState, event: GateDecided) -> None:
    """Legacy in-process bucket write — tests only."""
    warnings.warn(
        "record_event_to_state is deprecated; use record_gate_decided (Session SSOT)",
        DeprecationWarning,
        stacklevel=2,
    )
    view = PerceiveState.from_agent_state(state)
    view.gate_decided.append(event)
    view.commit(state)
