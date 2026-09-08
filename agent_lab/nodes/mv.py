"""Model-visible assembly nodes.

These are the workers in the mv.assemble sub-graph (ADR-0206 §5.3).
"""

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


@node(
    id="merge_messages",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.ASSEMBLER,
    description="Combine multiple message-list artifacts into one ordered list.",
    inputs=[PortInfo("any_in", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
    provides=["merged_messages"],
    requires=["message_list"],
    relates_to=["assemble_messages", "commit_manifest", "validate_manifest"],
)
class MergeMessages(Node):
    """Combine multiple message-list artifacts into one ordered list."""

    name = "merge_messages"

    def execute(self, node, inputs):
        out_port = node.outs[0]
        order = node.config.get("order", list(inputs.keys()))
        merged: list = []
        for k in order:
            a = inputs.get(k)
            if a is None:
                continue
            content = a.content
            if isinstance(content, list):
                merged.extend(content)
            elif isinstance(content, str):
                merged.append({"role": k, "content": content})
            else:
                merged.append({"role": k, "content": str(content)})
        return {out_port: Artifact(
            kind=ArtifactKind.MESSAGE,
            content=merged,
            schema_ref="openai.messages.v1",
        )}

@node(
    id="validate_manifest",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.VALIDATOR,
    description="Sanity-check that messages are non-empty and contain required roles.",
    inputs=[PortInfo("from", kind=PortKind.MESSAGE, required=False)],
    outputs=[PortInfo("validation", kind=PortKind.FACT)],
    provides=["manifest_validation"],
    requires=["message_list"],
    relates_to=["commit_manifest", "merge_messages"],
)
class ValidateManifest(Node):
    """Sanity-check that messages are non-empty and contain required roles."""

    name = "validate_manifest"

    def execute(self, node, inputs):
        out_port = node.outs[0]
        src = node.config.get("from", node.ins[0])
        required_roles = node.config.get("required_roles", [])
        src_a = inputs.get(src)
        messages = src_a.content if src_a else []
        roles = {m.get("role") for m in messages if isinstance(m, dict)}
        ok = all(r in roles for r in required_roles)
        return {out_port: Artifact(
            kind=ArtifactKind.FACT,
            content={"valid": ok, "missing": [r for r in required_roles if r not in roles]},
            schema_ref="manifest.validate.v1",
        )}
