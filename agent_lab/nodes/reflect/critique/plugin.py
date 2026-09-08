"""reflect.critique — Critic.critique(state, observation) → Reflection.

The only cognitive judgment in the reflect phase. Emits a Reflection
artifact; does not write memory or Session.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="reflect.critique",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Call LCA Critic.critique via LcaReflectCriticProvider; "
        "emit a Reflection (verdict / lesson / correction)."
    ),
    inputs=[PortInfo("combined", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("reflection", kind=PortKind.FACT)],
    provides=["reflection"],
    requires=["critic"],
    emits=["reflection"],
    relates_to=["reflect.join", "reflect.extract"],
)
class ReflectCritique(Node):
    name = "reflect.critique"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_reflect import LcaReflectCriticProvider

        provider = LcaReflectCriticProvider.from_node_config(getattr(node, "config", None) or {})
        src = (getattr(node, "config", None) or {}).get("from", "combined")
        combined = inputs.get(src) or inputs.get("combined")
        return provider.critique(combined_artifact=combined)
