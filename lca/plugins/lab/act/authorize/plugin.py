# PR-B — act.authorize node plugin (minimal stub for loader registration)
"""act.authorize — Intent → stamped Intent with grant verdict.

Stub plugin marker; full implementation reaches via node factory.
PR-D will rewrite this as a full @plugin carrier.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "authorize", "stage": "act"}
_LAB_HOOKS["lab.act.authorize"] = _marker

__all__ = ["_marker"]

# --- PR-D worker execute -----------------------------------------------
from lca.plugins.lab.internal.worker import Worker, register_worker
from agent_lab.primitives.artifact import Artifact, ArtifactKind

class _ActAuthorize(Worker):
    factory = "act.authorize"

    def execute(self, node, inputs, seams=None):
        from agent_lab.primitives.artifact import Artifact, ArtifactKind
        out_port = node.config.get("to", "authorized")
        intent_a = inputs.get(node.config.get("from", "intent"))
        content = intent_a.content if intent_a is not None and isinstance(intent_a.content, dict) else {}
        allow = set(node.config.get("allow", []) or [])
        effect_kind = str(content.get("effect_kind") or "")
        tool = content.get("tool")
        if effect_kind == "no_effect":
            verdict = "skip"
        elif effect_kind in ("respond","stop","ask_human","delegate","handoff"):
            verdict = "allow"
        elif effect_kind in ("use_tool","call_tool"):
            verdict = "allow" if tool in allow else "deny"
        else:
            verdict = "skip"
        stamped = {**content, "verdict": verdict, "tool": tool}
        return {out_port: Artifact(kind=ArtifactKind.INTENT, content=stamped, schema_ref="tool.intent.v1")}

register_worker("act.authorize", _ActAuthorize)
register_worker("lab.act.authorize", _ActAuthorize)
