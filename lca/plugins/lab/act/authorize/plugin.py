# PR-B — act.authorize node plugin (minimal stub for loader registration)
"""act.authorize — Intent → stamped Intent with grant verdict.

Stub plugin marker; full implementation reaches via node factory.
PR-D will rewrite this as a full @plugin carrier.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "authorize", "stage": "act"}
_LAB_HOOKS["lab.act.authorize"] = _marker

__all__ = ["_marker"]