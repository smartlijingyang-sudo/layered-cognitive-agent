"""act.body — LabCarrier stub (PR-D).

Minimal real carrier: declares identity for the loader and exposes a
Worker subclass with the live execute() body. Real node logic lives in
the Worker; the LabCarrier binds slot id + aliases for loader + invoke.
"""

from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier
from lca.plugins.lab.internal.worker import Worker, register_worker
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_CARRIER = LabCarrier(
    id="lab.act.body",
    stage="act",
    kind="EXECUTOR",
    description="act.body worker (PR-D stub carrier + worker).",
    node_id="body",
    source_module="lca.plugins.lab.act.body.plugin",
    source_class="_ActBody",
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


class _ActBody(Worker):
    factory = "act.body"
    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.act.body_provider import get_body
        intent_a = inputs.get("authorized")
        content = intent_a.content if intent_a is not None and isinstance(intent_a.content, dict) else {}
        tool_name = content.get("tool")
        try:
            body = get_body()
            result = body.act(intent=content, plan_ref="lab-act")
            return {"receipt": Artifact(kind=ArtifactKind.RECEIPT, content={"status": "ok", "tool": tool_name, "decision_id": content.get("decision_id", ""), "result": result}, schema_ref="tool.receipt.v1")}
        except Exception as exc:
            return {"receipt": Artifact(kind=ArtifactKind.RECEIPT, content={"status": "error", "tool": tool_name, "error": str(exc)}, schema_ref="tool.receipt.v1")}


register_worker("act.body", _ActBody)
register_worker("lab.act.body", _ActBody)
