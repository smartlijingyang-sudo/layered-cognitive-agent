"""write_extract — call MemorySystem.update(state, observation, reflection).

Calls through ``LcaReflectMemoryProvider`` so provider selection is data,
not code.  Emits ``reflect_signal`` for downstream barrier / junction.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import (
    NodeKind,
    NodeLayer,
    PortInfo,
    PortKind,
    node,
)


@node(
    id="write_extract",
    name="write_extract",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Call LCA MemorySystem.update(state, observation, reflection) via "
        "LcaReflectMemoryProvider and emit a reflect_signal."
    ),
    inputs=[
        PortInfo("reflection", kind=PortKind.FACT, required=False),
        PortInfo("memory_candidates", kind=PortKind.FACT, required=False),
    ],
    outputs=[
        PortInfo("reflection_out", kind=PortKind.FACT),
        PortInfo("memory_extract_out", kind=PortKind.FACT),
        PortInfo("reflect_signal", kind=PortKind.FACT),
    ],
    provides=["reflection_out", "memory_extract_out", "reflect_signal"],
    requires=["memory_system"],
    emits=["reflect_signal"],
    relates_to=["call_critic", "extract_memory"],
)
class WriteExtractNode(Node):
    """Bridge Reflection + memory candidates → MemorySystem.update."""

    name = "write_extract"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_reflect import LcaReflectMemoryProvider

        provider = LcaReflectMemoryProvider.from_node_config(node.config)
        reflection_artifact = inputs.get("reflection")
        memory_artifact = inputs.get("memory_candidates")
        return provider.write(
            reflection_artifact=reflection_artifact,
            memory_artifact=memory_artifact,
        )
