# PR-D — control/think_guard node plugin marker
"""control/think_guard node stub marker for the loader.

Mirrors the agent_lab.nodes.control/think_guard node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "think_guard", "stage": "control"}
_LAB_HOOKS["lab.control.think_guard"] = _marker

__all__ = ["_marker"]
