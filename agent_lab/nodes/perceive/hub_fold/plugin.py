"""perceive__hub_fold — 1 in 1 out: AgentState -> frozen ContextManifest.

Calls Hub.perceive(state). The Hub is the SOLE emitter of ContextManifest
(per LCA contracts). This node never constructs ContextManifest by hand.

Stub: returns input as-is. Real impl imports SequentialPerceiveHub.
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive__hub_fold",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.EXECUTOR,
    description="Call Hub.perceive(state); emit frozen ContextManifest.",
    inputs=[PortInfo("state", kind=PortKind.FACT)],
    outputs=[PortInfo("manifest", kind=PortKind.MANIFEST)],
    provides=["context_manifest"],
    requires=["perceive_hub"],
)
class HubFold(Node):
    name = "perceive__hub_fold"

    def execute(self, node, inputs):
        return {"manifest": inputs.get("state")}
