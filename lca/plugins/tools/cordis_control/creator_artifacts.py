"""Creator-local Artifact values and lifecycle validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.artifact_state import ArtifactState
from lca.contracts.harness.journal.artifact import CapabilityArtifact


@dataclass(frozen=True, slots=True)
class AuthoredPlugin:
    """One source-loaded plugin and its current four-state Artifact."""

    artifact: CapabilityArtifact
    source: str
    path: str
    language: str
    factory: Any
    metadata: dict[str, Any]


def with_artifact(authored: AuthoredPlugin, artifact: CapabilityArtifact) -> AuthoredPlugin:
    """Replace only the immutable lifecycle value for an authored plugin."""

    return AuthoredPlugin(
        artifact=artifact,
        source=authored.source,
        path=authored.path,
        language=authored.language,
        factory=authored.factory,
        metadata=authored.metadata,
    )


def require_artifact(
    authored: dict[str, AuthoredPlugin], name: str, expected: ArtifactState
) -> AuthoredPlugin:
    """Return an Artifact only when it is in the next required lifecycle state."""

    try:
        item = authored[name]
    except KeyError as exc:
        raise ValueError(f"creator artifact {name!r} has not been authored") from exc
    if item.artifact.state is not expected:
        raise ValueError(
            f"creator artifact {name!r} is {item.artifact.state.value!r}; "
            f"expected {expected.value!r}"
        )
    return item


__all__ = ["AuthoredPlugin", "require_artifact", "with_artifact"]
