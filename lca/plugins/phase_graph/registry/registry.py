# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.registry.registry,
#        to: lca.plugins.loop.graph.nodes.registry.plugin,
#        delete_when: rg 'phase_graph\.registry' lca/ tests/ bundles/ = 0,
#        forbidden_new_usage: true)
"""Legacy re-export; SSOT is ``lca.plugins.loop.graph.nodes.registry.plugin``."""

from lca.plugins.loop.graph.nodes.registry.plugin import Config, GraphNodeExecutorRegistry, setup

__all__ = ["Config", "GraphNodeExecutorRegistry", "setup"]
