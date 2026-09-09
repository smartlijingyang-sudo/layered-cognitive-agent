# PR-D — passthrough/select_v2 node plugin marker
"""passthrough/select_v2 node stub marker for the loader.

Mirrors the agent_lab.nodes.passthrough/select_v2 node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "select_v2", "stage": "passthrough"}
_LAB_HOOKS["lab.passthrough.select_v2"] = _marker

__all__ = ["_marker"]
