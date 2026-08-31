"""Typed adapter for the closed capability set used by built-in phase executors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from lca.contracts.protocols.act.embodiment import Body
from lca.contracts.protocols.declarative.declarative_execution import (
    PhaseCapabilityReader,
    StandardPhaseCapability,
)
from lca.contracts.protocols.memory.memory import MemorySystem
from lca.contracts.protocols.runtime.runtime import StopPolicy
from lca.contracts.protocols.think.cognition import Brain, PerceiveHub


@dataclass(frozen=True, slots=True)
class StandardPhaseCapabilities:
    """Expose only the typed dependencies of standard phase execution.

    The generic ``PhaseCapabilityReader`` remains the interpreter interface.
    This adapter owns the closed-name lookup and casts once, so individual phase
    branches do not leak string keys or dynamic access into their logic.
    """

    reader: PhaseCapabilityReader

    @property
    def brain(self) -> Brain | None:
        return cast("Brain | None", self.reader.get(StandardPhaseCapability.BRAIN))

    @property
    def body(self) -> Body | None:
        return cast("Body | None", self.reader.get(StandardPhaseCapability.BODY))

    @property
    def memory(self) -> MemorySystem | None:
        return cast("MemorySystem | None", self.reader.get(StandardPhaseCapability.MEMORY))

    @property
    def perceive_hub(self) -> PerceiveHub | None:
        return cast(
            "PerceiveHub | None",
            self.reader.get(StandardPhaseCapability.PERCEIVE_HUB),
        )

    @property
    def stop_policy(self) -> StopPolicy | None:
        return cast("StopPolicy | None", self.reader.get(StandardPhaseCapability.STOP_POLICY))


__all__ = ["StandardPhaseCapabilities"]
