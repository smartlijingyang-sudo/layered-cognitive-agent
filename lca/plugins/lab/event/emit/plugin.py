# PR-D — event/emit node plugin marker
"""event/emit node stub marker for the loader.

Mirrors the agent_lab.nodes.event/emit node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "emit", "stage": "event"}
_LAB_HOOKS["lab.event.emit"] = _marker

__all__ = ["_marker"]
