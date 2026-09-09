# PR-D — lineage/trace_subgraph_exit node plugin marker
"""lineage/trace_subgraph_exit node stub marker for the loader.

Mirrors the agent_lab.nodes.lineage/trace_subgraph_exit node id so the graph compiler and
runner can resolve the factory via the loader. Full plugin carrier
rewrite lands in a follow-up PR — for now this marker lets the loader
recognise every remaining factory and the capability-closed-set test
passes for the lab Profile.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "trace_subgraph_exit", "stage": "lineage"}
_LAB_HOOKS["lab.lineage.trace_subgraph_exit"] = _marker

__all__ = ["_marker"]
