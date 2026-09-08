"""perceive_build node — call LcaPerceiveProvider and freeze ContextManifest.

A single ant-worker: read `sanitized` + `state` artifacts, run
Hub.perceive(state) through the resolved provider, and emit one
MANIFEST artifact carrying the frozen ContextManifest.

Provider selection is data, not code; see
``agent_lab/graphs/configs/perceive.yaml`` for the canonical call site.
The Hub is the SOLE emitter of ContextManifested (per LCA contracts);
this node never constructs a ContextManifest by hand.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import (
    NodeKind,
    NodeLayer,
    PortInfo,
    PortKind,
    node,
)
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="perceive_build",
    name="perceive_build",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Resolve LcaPerceiveProvider from node.config, call Hub.perceive(state) "
        "on the AgentState coerced from the state artifact, and emit a frozen "
        "ContextManifest as a MANIFEST artifact."
    ),
    inputs=[
        PortInfo("sanitized", kind=PortKind.ARTIFACT, required=False),
        PortInfo("state", kind=PortKind.ARTIFACT, required=False),
    ],
    outputs=[PortInfo("manifest", kind=PortKind.MANIFEST)],
    provides=["perceive_manifest"],
    requires=["perceive_hub"],
    emits=["context_manifest"],
    relates_to=["trust_classify", "dedup", "rank", "redact"],
)
class PerceiveBuild(Node):
    """Single ant-worker that delegates to LcaPerceiveProvider.

    Adapter pattern: agent_lab does not import any LCA implementation at
    module-load time; the import is lazy (via
    ``agent_lab.adapters.lca_perceive.LcaPerceiveProvider``) so the
    framework can still boot without lca installed. Fixtures inject a
    Hub directly via ``provider_config.fixture_hub``; production profiles
    inject ``provider_config.hub_factory``.
    """

    name = "perceive_build"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_perceive import LcaPerceiveProvider

        provider = LcaPerceiveProvider.from_node_config(node.config)
        out_port = node.config.get("to", node.outs[0] if node.outs else "manifest")
        sanitized = inputs.get("sanitized")
        state = inputs.get("state")
        # If the upstream is empty (e.g. classify produced no labels), still
        # build the artifact so the manifest is frozen for downstream.
        if sanitized is None:
            sanitized = Artifact(kind=ArtifactKind.TEXT, content="")
        return provider.build(
            sanitized_artifact=sanitized,
            state_artifact=state,
            out_port=out_port,
        )
