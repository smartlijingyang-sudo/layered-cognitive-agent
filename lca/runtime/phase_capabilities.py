"""Own the runtime phase capability projection seam.

Composition provides canonical graph facts and declared contributions. This
module decides how those facts become the restricted capability view consumed
by the declarative interpreter, including rejection of divergent duplicates.
"""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.protocols.think.cognition import Brain, PerceiveHub
from lca.contracts.protocols.act.embodiment import Body
from lca.contracts.protocols.memory.memory import MemorySystem
from lca.runtime.runtime_bindings import RuntimePhaseCapabilities


def project_runtime_phase_capabilities(
    *,
    phase_capabilities: Mapping[str, object],
    brain: Brain,
    body: Body,
    memory: MemorySystem,
    perceive_hub: PerceiveHub,
) -> RuntimePhaseCapabilities:
    """Project graph facts into one frozen phase capability view."""

    canonical = {
        "brain": brain,
        "body": body,
        "memory": memory,
        "perceive_hub": perceive_hub,
    }
    conflicting = sorted(
        name
        for name, value in canonical.items()
        if name in phase_capabilities and phase_capabilities[name] is not value
    )
    if conflicting:
        raise ValueError(
            "RuntimePhaseCapabilities phase capability conflicts with canonical graph fact: "
            + ", ".join(conflicting)
        )
    return RuntimePhaseCapabilities({**phase_capabilities, **canonical})


__all__ = ["project_runtime_phase_capabilities"]
