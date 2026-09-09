# PR-D — session_log/flush_sink node plugin marker
"""session_log/flush_sink node stub marker for the loader.

Mirrors the agent_lab.nodes.session_log/flush_sink node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "flush_sink", "stage": "session_log"}
_LAB_HOOKS["lab.session_log.flush_sink"] = _marker

__all__ = ["_marker"]
