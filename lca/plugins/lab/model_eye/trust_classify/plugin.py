# PR-D — model_eye/trust_classify node plugin marker
"""model_eye/trust_classify node stub marker for the loader.

Mirrors the agent_lab.nodes.model_eye/trust_classify node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "trust_classify", "stage": "model_eye"}
_LAB_HOOKS["lab.model_eye.trust_classify"] = _marker

__all__ = ["_marker"]
