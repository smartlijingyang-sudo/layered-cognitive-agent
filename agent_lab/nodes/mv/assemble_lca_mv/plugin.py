"""assemble_lca_mv node — invoke LCA DefaultModelContextAssembler.assemble()."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node

_LCA_MV_PROVIDERS: dict[str, object] = {}


def register_lca_mv_provider(name: str, provider) -> None:
    _LCA_MV_PROVIDERS[name] = provider


def _default_lca_mv_provider() -> object:
    """Lazy-build a DefaultModelContextAssembler-backed provider."""
    if "default" not in _LCA_MV_PROVIDERS:
        from agent_lab.adapters.lca_mv import LcaMvProvider

        _LCA_MV_PROVIDERS["default"] = LcaMvProvider()
    return _LCA_MV_PROVIDERS["default"]


@node(
    id="assemble_lca_mv",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Build a SessionReader from agent_lab artifacts, invoke LCA "
        "DefaultModelContextAssembler.assemble(), and emit a manifest artifact "
        "shaped like ModelVisibleRequest (messages/system/config/tools)."
    ),
    inputs=[
        PortInfo("messages", kind=PortKind.MESSAGE, required=False),
        PortInfo("system", kind=PortKind.TEXT, required=False),
        PortInfo("config", kind=PortKind.FACT, required=False),
        PortInfo("tools", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("manifest", kind=PortKind.MANIFEST)],
    provides=["lca_model_visible_request"],
    requires=["message_list", "system_prompt"],
    consumes=[],
    emits=["context_manifest"],
    relates_to=["commit_manifest", "merge_messages", "assemble_messages"],
)
class AssembleLcaMv(Node):
    """Wire agent_lab into LCA's DefaultModelContextAssembler.

    Adapter pattern: agent_lab does not import any LCA implementation here
    at module-load time; the import is lazy so the framework can still
    boot without lca installed.
    """

    name = "assemble_lca_mv"

    def execute(self, node, inputs):
        provider_name = node.config.get("provider", "default")
        provider = _LCA_MV_PROVIDERS.get(provider_name) or _default_lca_mv_provider()
        out_port = node.config.get("to", "manifest")
        step = int(node.config.get("step", 0))
        return {
            out_port: provider.assemble(
                messages_artifact=inputs.get("messages"),
                system_artifact=inputs.get("system"),
                config_artifact=inputs.get("config"),
                tools_artifact=inputs.get("tools"),
                step=step,
            )
        }
