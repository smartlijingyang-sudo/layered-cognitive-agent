# PR-D — control/perceive_context_node node plugin marker
"""control/perceive_context_node node stub marker for the loader.

Mirrors the agent_lab.nodes.control/perceive_context_node node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "perceive_context_node", "stage": "control"}
_LAB_HOOKS["lab.control.perceive_context_node"] = _marker

__all__ = ["_marker"]
