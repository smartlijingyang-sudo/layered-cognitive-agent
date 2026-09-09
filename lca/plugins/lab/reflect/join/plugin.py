# PR-D — reflect/join node plugin marker
"""reflect/join node stub marker for the loader.

Mirrors the agent_lab.nodes.reflect/join node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "join", "stage": "reflect"}
_LAB_HOOKS["lab.reflect.join"] = _marker

__all__ = ["_marker"]
