"""Own the runtime phase capability projection seam.

Composition provides canonical graph facts and declared contributions. This
module decides how those facts become the restricted capability view consumed
by the declarative interpreter, including rejection of divergent duplicates.
"""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.models.team.role.team import ToolPermissionManifest
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.act.embodiment.embodiment import Body
from lca.contracts.protocols.memory.memory import MemorySystem
from lca.contracts.protocols.think.cognition import Brain, PerceiveHub
from lca.runtime.support.runtime_bindings import RuntimePhaseCapabilities


def project_runtime_phase_capabilities(
    *,
    phase_capabilities: Mapping[str, object],
    brain: Brain,
    body: Body,
    memory: MemorySystem,
    perceive_hub: PerceiveHub,
    llm: LLMAdapter,
    permission_manifest: ToolPermissionManifest | None = None,
) -> RuntimePhaseCapabilities:
    """Project graph facts into one frozen phase capability view.

    ``phase.think.*`` prefixed keys from BrainComposer are additional
    composition-time projections. They do not share names with the canonical
    graph facts and therefore pass through without conflict.

    ``permission_manifest`` is profile-time policy, not graph fact. It is
    carried on the kernel runtime carrier so ``effect.pre_dispatch.envelope_check``
    can read the active manifest at visit time via typed port
    ``runtime.get("permission_manifest")`` (ADR-0220 PR-A). ``None`` is the
    fail-loud default — the envelope gate treats ``allowed=None`` as deny,
    matching the historical executor's "manifest missing → deny" branch.
    """

    # ``llm`` is the complete-graph fact for the LLMAdapter; the typed think
    # subgraph reads it under the kernel-runtime carrier key ``adapter``
    # (ADR-0220 PR-A). Aliasing here keeps composition-time single ownership
    # (``AgentGraph.llm``) while preserving the typed-port read path.
    canonical = {
        "brain": brain,
        "body": body,
        "memory": memory,
        "perceive_hub": perceive_hub,
        "adapter": llm,
        "permission_manifest": permission_manifest,
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
