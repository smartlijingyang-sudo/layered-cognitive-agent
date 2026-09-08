"""integrate_observation — passthrough that emits a receipt as an observation artifact.

The success/error text-template logic lives in
``agent_lab.plugins.observation.ObservationRenderPlugin``. This node
just emits a FACT carrying the raw receipt; the plugin's
``on_observation`` hook rewrites the artifact content with the rendered
text. Returning a TEXT artifact would let downstream consumers parse a
single line; keeping FACT (with the plugin's rewritten ``text`` field)
preserves the existing artifact schema_ref while exposing the
rendered string.

Backward-compat: when no ObservationRenderPlugin is configured, the
node still emits a FACT with the raw receipt — the caller's tooling
that reads ``artifact.content`` directly continues to work.
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
    id="integrate_observation",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Emit the raw receipt as an observation artifact. The success/"
        "error text-template logic lives in ObservationRenderPlugin (the "
        "on_observation hook)."
    ),
    inputs=[PortInfo("receipt_fact", kind=PortKind.RECEIPT, required=False)],
    outputs=[PortInfo("observation", kind=PortKind.MANIFEST)],
    provides=["observation"],
    consumes=["consact"],
    relates_to=["dispatch_tool", "write_receipt", "merge_messages"],
)
class IntegrateObservation(Node):
    """Passthrough — emit the receipt as an observation artifact."""

    name = "integrate_observation"

    def execute(self, node, inputs):
        src = node.config.get("from", "receipt")
        out_port = node.config.get("to", "observation")
        receipt = inputs.get(src)
        if receipt is None:
            return {
                out_port: Artifact(
                    kind=ArtifactKind.MANIFEST,
                    content={},
                    schema_ref="observation.v1",
                )
            }
        # Rebuild as MANIFEST with schema_ref observation.v1 so the
        # runner's semantic-fanout (schema_ref → on_observation hook)
        # picks the right hook. We keep the raw receipt content as-is;
        # the plugin is responsible for adding ``text``.
        content = getattr(receipt, "content", {}) or {}
        if not isinstance(content, dict):
            content = {"raw": content}
        return {
            out_port: Artifact(
                kind=ArtifactKind.MANIFEST,
                content=content,
                schema_ref="observation.v1",
            )
        }
