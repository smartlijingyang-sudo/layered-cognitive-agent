# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.topology,
#        to: lca.plugins.loop.graph.nodes.topology.plugin,
#        delete_when: rg 'phase_graph\.topology\b' lca/ tests/ bundles/ = 0,
#        forbidden_new_usage: true)
"""Legacy flat re-export; SSOT is ``lca.plugins.loop.graph.nodes.topology.plugin``."""

from lca.plugins.loop.graph.nodes.topology.plugin import Config, TopologyGraphNodeExecutor, setup

__all__ = ["Config", "TopologyGraphNodeExecutor", "setup"]
