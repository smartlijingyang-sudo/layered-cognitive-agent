# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.agent.agent,
#        to: lca.plugins.loop.graph.nodes.agent.plugin,
#        delete_when: rg 'phase_graph\.agent' lca/ tests/ bundles/ = 0,
#        forbidden_new_usage: true)
"""Legacy re-export; SSOT is ``lca.plugins.loop.graph.nodes.agent.plugin``."""

from lca.plugins.loop.graph.nodes.agent.plugin import AgentGraphNodeExecutor, Config, setup

__all__ = ["AgentGraphNodeExecutor", "Config", "setup"]
