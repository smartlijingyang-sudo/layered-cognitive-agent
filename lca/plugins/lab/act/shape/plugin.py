# PR-B — act.shape node plugin (minimal stub for loader registration)
"""act.shape — Decision → Intent for Body.act.

Stub plugin that registers a marker for the act.shape node in the
loader. The actual implementation lives in agent_lab/nodes/act/shape/
plugin.py and is reached via the node factory (not the plugin system).
PR-D will rewrite this as a full @plugin carrier.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "shape", "stage": "act"}
_LAB_HOOKS["lab.act.shape"] = _marker

__all__ = ["_marker"]

# --- PR-D worker execute -----------------------------------------------
from lca.plugins.lab.internal.worker import Worker, register_worker
from agent_lab.primitives.artifact import Artifact, ArtifactKind

class _ActShape(Worker):
    factory = "act.shape"

    def execute(self, node, inputs, seams=None):
        from agent_lab.primitives.artifact import Artifact, ArtifactKind
        out_port = node.config.get("to", "intent")
        decision_a = inputs.get(node.config.get("from", "decision"))
        raw = decision_a.content if decision_a is not None and isinstance(decision_a.content, dict) else {}
        # Minimal shape: copy decision into intent artifact.
        return {out_port: Artifact(kind=ArtifactKind.INTENT, content=dict(raw), schema_ref="tool.intent.v1")}

register_worker("act.shape", _ActShape)
register_worker("lab.act.shape", _ActShape)
