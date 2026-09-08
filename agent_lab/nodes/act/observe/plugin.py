"""act.observe — EffectReceipt | EXCEPTION → Observation.

Single exit for success, deny, no_effect, and on_error=route. Does not
write Journal (remember owns durable facts) and does not re-execute.
Text rendering is owned by ObservationRenderPlugin when present.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="act.observe",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Receipt (or EXCEPTION from on_error=route) → observation.v1. "
        "Unified success/deny/error/no_effect exit for the act phase."
    ),
    inputs=[
        PortInfo("receipt", kind=PortKind.RECEIPT, required=False),
        PortInfo("exception", kind=PortKind.ARTIFACT, required=False),
    ],
    outputs=[PortInfo("observation", kind=PortKind.MANIFEST)],
    provides=["observation"],
    consumes=["effect_receipt"],
    relates_to=["act.execute", "model_eye.see"],
)
class ActObserve(Node):
    """Normalize receipt or routed exception into an observation artifact."""

    name = "act.observe"

    def execute(self, node, inputs):
        out_port = node.config.get("to", "observation")
        # on_error=route seeds the target's first IN port (receipt). Also
        # accept an explicit exception port for clarity in YAML.
        receipt = inputs.get(node.config.get("from", "receipt"))
        exception = inputs.get("exception")

        if _is_exception(receipt):
            content = _exception_to_receipt_content(receipt)
        elif _is_exception(exception):
            content = _exception_to_receipt_content(exception)
        elif receipt is None:
            content = {}
        else:
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


def _is_exception(artifact: Any) -> bool:
    if artifact is None:
        return False
    kind = getattr(artifact, "kind", None)
    if kind == ArtifactKind.EXCEPTION:
        return True
    schema = getattr(artifact, "schema_ref", "") or ""
    return schema.startswith("exception")


def _exception_to_receipt_content(artifact: Any) -> dict[str, Any]:
    raw = getattr(artifact, "content", {}) or {}
    if not isinstance(raw, dict):
        return {"status": "error", "error": str(raw)}
    # Runner wraps routed exceptions as {handled, original:{...}}.
    original = raw.get("original") if isinstance(raw.get("original"), dict) else raw
    return {
        "status": "error",
        "error": str(
            original.get("message")
            or original.get("error")
            or original.get("error_class")
            or "routed exception"
        ),
        "error_class": original.get("error_class"),
        "node_id": original.get("node_id"),
    }
