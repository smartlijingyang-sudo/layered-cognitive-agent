"""Tests for the typed adapter used by built-in phase executors."""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.protocols.declarative.declarative_execution import StandardPhaseCapability
from lca.plugins.phase_executors.capabilities import StandardPhaseCapabilities


@dataclass
class _RecordingReader:
    values: dict[str, object]
    requested: list[str] = field(default_factory=list)

    def get(self, name: str) -> object | None:
        self.requested.append(name)
        return self.values.get(name)

    def require(self, name: str) -> object:
        value = self.get(name)
        if value is None:
            raise KeyError(name)
        return value


def test_standard_adapter_owns_closed_capability_names() -> None:
    brain = object()
    reader = _RecordingReader({StandardPhaseCapability.BRAIN: brain})

    capabilities = StandardPhaseCapabilities(reader)

    assert capabilities.brain is brain
    assert reader.requested == [StandardPhaseCapability.BRAIN]


def test_standard_adapter_returns_none_for_an_unbound_declared_capability() -> None:
    capabilities = StandardPhaseCapabilities(_RecordingReader({}))

    assert capabilities.memory is None
