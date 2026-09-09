"""act.receipt_denied — LabCarrier stub (PR-D).

Minimal real carrier: declares identity for the loader and exposes a
Worker subclass with the live execute() body. Real node logic lives in
the Worker; the LabCarrier binds slot id + aliases for loader + invoke.
"""

from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier
from lca.plugins.lab.internal.worker import Worker, register_worker
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_CARRIER = LabCarrier(
    id="lab.act.receipt_denied",
    stage="act",
    kind="EXECUTOR",
    description="act.receipt_denied worker (PR-D stub carrier + worker).",
    node_id="receipt_denied",
    source_module="lca.plugins.lab.act.receipt_denied.plugin",
    source_class="_ActReceiptDenied",
    provides=[],
    requires=[],
    emits=[],
    inputs=[],
    outputs=[],
    out_capabilities=[],
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


class _ActReceiptDenied(Worker):
    factory = "act.receipt_denied"
    def execute(self, node, inputs, seams=None):
        del seams
        c = getattr(inputs.get("authorized"), "content", {}) or {}
        if not isinstance(c, dict):
            c = {}
        return {"receipt": Artifact(kind=ArtifactKind.RECEIPT, content={"status": "denied", "tool": c.get("tool"), "decision_id": c.get("decision_id", ""), "action_type": str(c.get("action_type") or ""), "error": "grant denied"}, schema_ref="tool.receipt.v1")}


register_worker("act.receipt_denied", _ActReceiptDenied)
register_worker("lab.act.receipt_denied", _ActReceiptDenied)
