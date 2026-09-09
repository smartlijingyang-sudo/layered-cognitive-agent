# PR-B — act.observe node plugin (minimal stub for loader registration)
"""act.observe — EffectReceipt | EXCEPTION → Observation.

Stub plugin marker; full implementation reaches via node factory.
PR-D will rewrite this as a full @plugin carrier.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "observe", "stage": "act"}
_LAB_HOOKS["lab.act.observe"] = _marker

__all__ = ["_marker"]

# --- PR-D worker execute -----------------------------------------------
from lca.plugins.lab.internal.worker import Worker, register_worker
from agent_lab.primitives.artifact import Artifact, ArtifactKind

class _ActObserve(Worker):
    factory = "act.observe"

    def execute(self, node, inputs, seams=None):
        from agent_lab.primitives.artifact import Artifact, ArtifactKind
        out_port = node.config.get("to", "observation")
        receipt = inputs.get(node.config.get("from", "receipt"))
        exception = inputs.get("exception")
        if receipt is not None and getattr(receipt, "kind", None) == ArtifactKind.EXCEPTION:
            content = (getattr(receipt, "content", {}) or {})
            content = content.get("original", content) if isinstance(content, dict) else {"raw": content}
        elif exception is not None and getattr(exception, "kind", None) == ArtifactKind.EXCEPTION:
            content = (getattr(exception, "content", {}) or {})
            content = content.get("original", content) if isinstance(content, dict) else {"raw": content}
        elif receipt is None:
            content = {}
        else:
            content = getattr(receipt, "content", {}) or {}
            if not isinstance(content, dict):
                content = {"raw": content}
        return {out_port: Artifact(kind=ArtifactKind.MANIFEST, content=content, schema_ref="observation.v1")}

register_worker("act.observe", _ActObserve)
register_worker("lab.act.observe", _ActObserve)
