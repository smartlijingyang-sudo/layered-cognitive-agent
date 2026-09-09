"""perceive.memory — MemorySystem.perceive(state) → memory_items.

worker: memory(*, memory_artifact, state_artifact) -> memory_items
kind: TRANSFORMER
out_port: memory_items
in: memory_ref=memory_artifact state=state_artifact
"""
from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.perceive.ops import fold_memory_items


def memory(
    *,
    memory_artifact: Artifact | None,
    state_artifact: Artifact | None,
) -> dict[str, Artifact]:
    """Call MemorySystem.perceive(state) and project retrieved_context items."""
    return fold_memory_items(
        memory_artifact=memory_artifact,
        state_artifact=state_artifact,
    )


__all__ = ["memory"]
