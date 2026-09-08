"""registry_loader node — load tool entries from a YAML registry file.

Reads a YAML file (default: agent_lab/tools/registry.yaml) via
LcaToolboxRegistryProvider and emits a registry_payload FACT artifact
listing name → ref/kwargs/capability/scope for each tool.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="registry_loader",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.PRODUCER,
    description=(
        "Load tool entries from a YAML registry file and emit a registry_payload FACT artifact."
    ),
    inputs=[],
    outputs=[PortInfo("registry_payload", kind=PortKind.FACT)],
    provides=["tool_registry_payload"],
    relates_to=["trust_classify", "resolve_tool"],
)
class RegistryLoader(Node):
    """Load tools from a YAML registry via LcaToolboxRegistryProvider."""

    name = "registry_loader"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_toolbox import LcaToolboxRegistryProvider

        provider = LcaToolboxRegistryProvider.from_node_config(node.config)
        out_port = node.config.get("to", "registry_payload")
        return {out_port: provider.load(node.config)}
