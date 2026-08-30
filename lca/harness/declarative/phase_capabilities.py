"""Normalize the narrow capability view exposed to declarative phase executors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lca.contracts.protocols.declarative_execution import PhaseCapabilityReader


@dataclass(frozen=True, slots=True)
class MappingPhaseCapabilities(PhaseCapabilityReader):
    """Adapt a test mapping into the same narrow capability view as production."""

    values: Mapping[str, object]

    def get(self, name: str) -> object | None:
        return self.values.get(name)

    def require(self, name: str) -> object:
        """Return a capability or expose a deterministic seam error."""
        value = self.get(name)
        if value is None:
            raise KeyError(f"phase capability is not declared: {name}")
        return value


def normalize_phase_capabilities(
    capabilities: PhaseCapabilityReader | Mapping[str, object] | None,
) -> PhaseCapabilityReader:
    """Normalize public interpreter inputs before exposing them to a phase.

    The interpreter accepts a mapping for focused tests and a typed reader for
    production composition. Arbitrary objects are rejected instead of relying
    on runtime attribute guessing inside phase executors.
    """

    if capabilities is None:
        return MappingPhaseCapabilities({})
    if isinstance(capabilities, Mapping):
        return MappingPhaseCapabilities(capabilities)
    if isinstance(capabilities, PhaseCapabilityReader):
        return capabilities
    raise TypeError(
        "phase capabilities must implement PhaseCapabilityReader or be a mapping, "
        f"got {type(capabilities).__name__}"
    )


__all__ = ["MappingPhaseCapabilities", "normalize_phase_capabilities"]
