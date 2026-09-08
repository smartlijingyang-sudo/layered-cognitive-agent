"""perceive.commit — build ContextManifest + digest (Hub commit step)."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive.commit",
    layer=NodeLayer.PHASE,
    kind=NodeKind.PRODUCER,
    description=(
        "Build ContextManifest(items, digest) from trimmed Hub items. "
        "No Session write (observation-plane emit is owned elsewhere)."
    ),
    inputs=[PortInfo("trimmed_items", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("context_manifest", kind=PortKind.FACT)],
    provides=["context_manifest"],
    emits=["context_manifest"],
    relates_to=["perceive.trim", "model_eye.see"],
)
class PerceiveCommit(Node):
    name = "perceive.commit"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_perceive import commit_manifest

        del node
        return commit_manifest(trimmed_items=inputs.get("trimmed_items"))
