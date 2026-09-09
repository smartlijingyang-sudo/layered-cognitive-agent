# PR-D — model_eye/shape node plugin marker
"""model_eye/shape node stub marker for the loader.

Mirrors the agent_lab.nodes.model_eye/shape node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "shape", "stage": "model_eye"}
_LAB_HOOKS["lab.model_eye.shape"] = _marker

__all__ = ["_marker"]
