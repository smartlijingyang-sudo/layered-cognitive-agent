# PR-D — remember/commit node plugin marker
"""remember/commit node stub marker for the loader.

Mirrors the agent_lab.nodes.remember/commit node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "commit", "stage": "remember"}
_LAB_HOOKS["lab.remember.commit"] = _marker

__all__ = ["_marker"]
