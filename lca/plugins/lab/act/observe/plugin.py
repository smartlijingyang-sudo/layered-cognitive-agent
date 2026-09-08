# PR-B — act.observe node plugin (minimal stub for loader registration)
"""act.observe — EffectReceipt | EXCEPTION → Observation.

Stub plugin marker; full implementation reaches via node factory.
PR-D will rewrite this as a full @plugin carrier.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "act.observe", "stage": "act"}
_LAB_HOOKS["lab.act.observe"] = _marker

__all__ = ["_marker"]