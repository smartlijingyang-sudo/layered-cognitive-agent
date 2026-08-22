"""CapabilityArtifact and the four-state ArtifactController contract."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.atoms.artifact_state import LEGAL_TRANSITIONS, ArtifactState, is_legal_transition
from lca.contracts.atoms.scope import Scope, parse_scope


class InvalidStateTransitionError(ValueError):
    """Raised when a requested four-state Artifact transition is illegal."""


@dataclass(frozen=True, slots=True)
class CapabilityArtifact:
    """Immutable capability artifact governed by DRAFT, VERIFIED, ACTIVE and RETIRED."""

    logical_id: str
    revision_digest: str
    state: ArtifactState
    scope: Scope
    grants: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.logical_id, str) or not self.logical_id:
            raise ValueError(
                f"CapabilityArtifact.logical_id must be non-empty str, got {self.logical_id!r}"
            )
        if not isinstance(self.revision_digest, str) or not self.revision_digest:
            raise ValueError("CapabilityArtifact.revision_digest must be non-empty str")
        if not isinstance(self.state, ArtifactState):
            object.__setattr__(self, "state", ArtifactState(self.state))
        if not isinstance(self.scope, Scope):
            object.__setattr__(self, "scope", parse_scope(self.scope))
        if not isinstance(self.grants, tuple):
            object.__setattr__(self, "grants", tuple(self.grants))


def artifact_with_state(artifact: CapabilityArtifact, state: ArtifactState) -> CapabilityArtifact:
    """Return a new Artifact value with only its lifecycle state changed."""

    return CapabilityArtifact(
        logical_id=artifact.logical_id,
        revision_digest=artifact.revision_digest,
        state=state,
        scope=artifact.scope,
        grants=artifact.grants,
        metadata=artifact.metadata,
        version=artifact.version,
    )


def legal_next_states(artifact: CapabilityArtifact) -> tuple[ArtifactState, ...]:
    """Return legal target states in stable enum order."""

    return tuple(state for state in ArtifactState if (artifact.state, state) in LEGAL_TRANSITIONS)


def migrate_artifact(
    artifact: CapabilityArtifact, target_state: ArtifactState
) -> CapabilityArtifact:
    """Apply one legal state transition or fail without changing the Artifact."""

    if not is_legal_transition(artifact.state, target_state):
        legal = [state.value for state in legal_next_states(artifact)]
        raise InvalidStateTransitionError(
            f"CapabilityArtifact.logical_id={artifact.logical_id!r}: illegal state transition "
            f"{artifact.state.value!r} → {target_state.value!r}; legal targets: {legal or '(terminal)'}"
        )
    return artifact_with_state(artifact, target_state)


def migrate_to_verified(artifact: CapabilityArtifact) -> CapabilityArtifact:
    """Transition DRAFT to VERIFIED."""

    return migrate_artifact(artifact, ArtifactState.VERIFIED)


def migrate_to_active(artifact: CapabilityArtifact) -> CapabilityArtifact:
    """Transition VERIFIED to ACTIVE."""

    return migrate_artifact(artifact, ArtifactState.ACTIVE)


def migrate_to_retired(artifact: CapabilityArtifact) -> CapabilityArtifact:
    """Transition ACTIVE to RETIRED."""

    return migrate_artifact(artifact, ArtifactState.RETIRED)


def is_terminal_state(artifact: CapabilityArtifact) -> bool:
    """Return whether the Artifact cannot transition further."""

    return artifact.state is ArtifactState.RETIRED


def make_capability_artifact(
    logical_id: str,
    content: bytes | str,
    scope: Scope | str = Scope.RUN,
    state: ArtifactState | str = ArtifactState.DRAFT,
    grants: Iterable[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> CapabilityArtifact:
    """Create a four-state Artifact with a stable content revision digest."""

    content_bytes = content.encode("utf-8") if isinstance(content, str) else content
    return CapabilityArtifact(
        logical_id=logical_id,
        revision_digest=hashlib.sha256(content_bytes).hexdigest()[:16],
        state=ArtifactState(state),
        scope=parse_scope(scope) if isinstance(scope, str) else scope,
        grants=tuple(grants),
        metadata=dict(metadata) if metadata else {},
    )


def capability_artifact_to_dict(artifact: CapabilityArtifact) -> dict[str, Any]:
    """Return the JSON-safe representation used by Creator and diagnostics."""

    return {
        "logical_id": artifact.logical_id,
        "revision_digest": artifact.revision_digest,
        "state": artifact.state.value,
        "scope": artifact.scope.value,
        "grants": list(artifact.grants),
        "metadata": dict(artifact.metadata),
        "version": artifact.version,
    }


@dataclass(frozen=True, slots=True)
class ArtifactController:
    """Named facade for pure Artifact transition operations."""

    name: str = "default"


def controller_migrate(
    controller: ArtifactController,
    artifact: CapabilityArtifact,
    target_state: ArtifactState,
) -> CapabilityArtifact:
    """Apply a transition through the named controller facade."""

    del controller
    return migrate_artifact(artifact, target_state)


def controller_legal_next_states(
    controller: ArtifactController,
    artifact: CapabilityArtifact,
) -> tuple[ArtifactState, ...]:
    """Return allowed successor states through the controller facade."""

    del controller
    return legal_next_states(artifact)


__all__ = [
    "ArtifactController",
    "CapabilityArtifact",
    "InvalidStateTransitionError",
    "artifact_with_state",
    "capability_artifact_to_dict",
    "controller_legal_next_states",
    "controller_migrate",
    "is_terminal_state",
    "legal_next_states",
    "make_capability_artifact",
    "migrate_artifact",
    "migrate_to_active",
    "migrate_to_retired",
    "migrate_to_verified",
]
