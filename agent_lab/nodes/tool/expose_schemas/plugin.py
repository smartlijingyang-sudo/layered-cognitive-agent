"""expose_schemas — inventory → openai-style tool schemas for model-visible.

Owns the only conversion from ToolRegistry / registry_payload into the
frozen ``tools`` list that ``model_eye`` commits into ContextManifest.
No execution; pure projection of the named-tool inventory.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="expose_schemas",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Project tool inventory into openai-style function schemas "
        "(tools.v1) for model_eye.see / ContextManifest.tools."
    ),
    inputs=[PortInfo("registry_payload", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("tools", kind=PortKind.FACT)],
    provides=["tool_schemas"],
    requires=[],
    relates_to=["registry_loader", "model_eye.see", "think.reason"],
)
class ExposeSchemas(Node):
    name = "expose_schemas"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_toolbox import schemas_from_inventory

        out = node.config.get("to", "tools")
        schemas = schemas_from_inventory(
            registry_payload=inputs.get("registry_payload"),
            registry_path=node.config.get("registry_path"),
        )
        return {
            out: Artifact(
                kind=ArtifactKind.FACT,
                content=schemas,
                schema_ref="openai.tools.v1",
            )
        }
