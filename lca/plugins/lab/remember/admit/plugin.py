# PR-D — remember/admit node plugin marker
"""remember/admit node stub marker for the loader.

Mirrors the agent_lab.nodes.remember/admit node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "admit", "stage": "remember"}
_LAB_HOOKS["lab.remember.admit"] = _marker

__all__ = ["_marker"]
