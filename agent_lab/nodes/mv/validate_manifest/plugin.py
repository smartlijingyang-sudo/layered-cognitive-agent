"""validate_manifest node — sanity-check that messages are non-empty and contain required roles."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


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
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content={"valid": ok, "missing": [r for r in required_roles if r not in roles]},
                schema_ref="manifest.validate.v1",
            )
        }
