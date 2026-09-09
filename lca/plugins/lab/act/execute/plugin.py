# PR-B — act.execute node plugin (minimal stub for loader registration)
"""act.execute — authorized Intent → EffectReceipt via SimpleBody.act.

Stub plugin marker; full implementation reaches via node factory.
PR-D will rewrite this as a full @plugin carrier. The Body
composition stays in agent_lab.nodes.act.execute.body until PR-D.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "execute", "stage": "act", "needs": ["lab.body", "lab.tool_registry", "lab.safe_executor", "lab.transport", "lab.plan_ref"]}
_LAB_HOOKS["lab.act.execute"] = _marker

__all__ = ["_marker"]