"""resolve_tool node — resolve a tool name to a Tool instance.

Takes in_tool_name (string) and registry data from the upstream chain.
Uses LcaToolboxResolveProvider to look up the tool in a ToolRegistry
(either a fixture registered by name, or built from registry_payload).

Emits a tool_instance FACT artifact with the resolved Tool metadata.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="resolve_tool",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Resolve a tool name to a Tool instance using LcaToolboxResolveProvider. "
        "Emits tool_instance FACT with name, capability, scope metadata."
    ),
    inputs=[
        PortInfo("in_tool_name", kind=PortKind.TEXT),
        PortInfo("registry_data", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("tool_instance", kind=PortKind.FACT)],
    provides=["tool_resolve"],
    requires=["tool_registry"],
    relates_to=["registry_loader", "dispatch_tool"],
)
class ResolveTool(Node):
    """Resolve a tool name to its Tool instance via LcaToolboxResolveProvider."""

    name = "resolve_tool"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_toolbox import LcaToolboxResolveProvider

        provider = LcaToolboxResolveProvider.from_node_config(node.config)
        out_port = node.config.get("to", "tool_instance")
        tool_name_artifact = inputs.get("in_tool_name")
        registry_artifact = inputs.get("registry_data")
        return {
            out_port: provider.resolve(
                tool_name_artifact=tool_name_artifact,
                registry_artifact=registry_artifact,
            )
        }
