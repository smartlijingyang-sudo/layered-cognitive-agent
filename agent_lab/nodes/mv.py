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
        return {out_port: provider.assemble(
            messages_artifact=inputs.get("messages"),
            system_artifact=inputs.get("system"),
            config_artifact=inputs.get("config"),
            tools_artifact=inputs.get("tools"),
            step=step,
        )}
