"""act.dispatch — LabCarrier stub (PR-D).

Minimal real carrier: declares identity for the loader and exposes a
Worker subclass with the live execute() body. Real node logic lives in
the Worker; the LabCarrier binds slot id + aliases for loader + invoke.
"""

from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier
from lca.plugins.lab.internal.worker import Worker, register_worker
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_CARRIER = LabCarrier(
    id="lab.act.dispatch",
    stage="act",
    kind="EXECUTOR",
    description="act.dispatch worker (PR-D stub carrier + worker).",
    node_id="dispatch",
    source_module="lca.plugins.lab.act.dispatch.plugin",
    source_class="_ActDispatch",
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


class _ActDispatch(Worker):
    factory = "act.dispatch"
    def execute(self, node, inputs, seams=None):
        src = node.config.get("from", "authorized")
        intent = inputs.get(src)
        if intent is None:
            return {}
        content = getattr(intent, "content", None)
        verdict = content.get("verdict") if isinstance(content, dict) else None
        if verdict == "allow":
            port = "to_body"
        elif verdict == "deny":
            port = "to_denied"
        else:
            port = "to_none"
        return {port: intent}


register_worker("act.dispatch", _ActDispatch)
register_worker("lab.act.dispatch", _ActDispatch)
