"""Typed state slots for the PerceiveHub fold (PR3a / PR4).

The v3 spec forbids ad-hoc ``state.extra[key]`` magic strings.  This
module is the typed home for the *running* artifacts that the Hub
produces / consumes per step:

- ``current_manifest`` — the ContextManifest the Hub emits (read by
  the Reasoner).
- ``gate_decided`` — the running bucket of ``GateDecided`` events the
  Hub drains on each fold.

The dataclass ``PerceiveState`` is the typed container; an attribute
``PerceiveState.from_agent_state(state)`` adapts the legacy
``state.extra`` to the typed slot.  This is the only sanctioned
backwards-compat path during the v3 rollout.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState

# Magic strings (legacy) — these are the only keys the v3 runtime is
# allowed to write into ``state.extra``.  Any new key must be added here
# AND migrated to a typed slot.
LEGACY_GATE_DECIDED_KEY = "gate_decided"
LEGACY_CURRENT_MANIFEST_KEY = "current_manifest"


@dataclass
class PerceiveState:
    """Typed view over the perception-related state slots.

    The Hub writes ``current_manifest`` on each perceive and drains
    ``gate_decided`` on each fold.  The Reasoner reads
    ``current_manifest`` to render the prompt.

    The class is a *view*: it does not own its own state.  Mutations
    are written back to ``AgentState.extra`` via ``commit()``.
    """

    current_manifest: ContextManifest | None = None
    gate_decided: list[GateDecided] = field(default_factory=list)

    @classmethod
    def from_agent_state(cls, state: AgentState) -> PerceiveState:
        """Read the typed slots from ``state.extra`` (legacy path)."""
        manifest = state.extra.get(LEGACY_CURRENT_MANIFEST_KEY)
        bucket = state.extra.get(LEGACY_GATE_DECIDED_KEY) or []
        if not isinstance(bucket, list):
            bucket = []
        # Normalize bucket to a list of GateDecided.
        normalized: list[GateDecided] = [item for item in bucket if isinstance(item, GateDecided)]
        return cls(
            current_manifest=manifest if isinstance(manifest, ContextManifest) else None,
            gate_decided=normalized,
        )

    def commit(self, state: AgentState) -> None:
        """Write the typed slots back to ``state.extra`` (legacy path)."""
        state.extra[LEGACY_CURRENT_MANIFEST_KEY] = self.current_manifest
        state.extra[LEGACY_GATE_DECIDED_KEY] = list(self.gate_decided)


def record_event_to_state(state: AgentState, event: GateDecided) -> None:
    """Append a single ``GateDecided`` to the running bucket (typed API).

    This is the canonical entry point every DecisionGate call site uses.
    The implementation lives in the typed module so the magic key is
    not duplicated across the codebase.
    """
    view = PerceiveState.from_agent_state(state)
    view.gate_decided.append(event)
    view.commit(state)
