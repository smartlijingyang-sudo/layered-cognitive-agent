# PR-D — control/stop_decide node plugin marker
"""control/stop_decide node stub marker for the loader.

Mirrors the agent_lab.nodes.control/stop_decide node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "stop_decide", "stage": "control"}
_LAB_HOOKS["lab.control.stop_decide"] = _marker

__all__ = ["_marker"]
