"""trust_classify node — tag every input with a trust label (trusted/untrusted)."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="trust_classify",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.VALIDATOR,
    description="Tag inputs with trust level (config.trustable_kinds:[str]).",
    inputs=[PortInfo("any_in", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("labels", kind=PortKind.FACT)],
    provides=["trust_labels"],
    relates_to=["redact", "merge_messages", "validate_manifest"],
)
class TrustClassify(Node):
    """Tag inputs with trust level (config.trustable_kinds:[str])."""

    name = "trust_classify"

    def execute(self, node, inputs):
        trustable = set(node.config.get("trustable_kinds", []))
        out_port = node.outs[0]
        labeled = []
        for k, a in inputs.items():
            label = "trusted" if a.kind.value in trustable else "untrusted"
            labeled.append({"port": k, "kind": a.kind.value, "trust": label, "digest": a.short_id()})
        return {out_port: Artifact(
            kind=ArtifactKind.FACT,
            content=labeled,
            schema_ref="trust.labels.v1",
        )}
