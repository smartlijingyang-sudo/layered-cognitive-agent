# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.stop.stop_policy,
#        to: lca.plugins.loop.state.stop_policy.plugin,
#        delete_when: rg 'phase_graph\.stop\.stop_policy' lca/ tests/ bundles/ = 0,
#        forbidden_new_usage: true)
"""Legacy nested re-export; SSOT is ``lca.plugins.loop.state.stop_policy.plugin``."""

from lca.plugins.loop.state.stop_policy.plugin import Config, DefaultStopPolicy, setup

__all__ = ["Config", "DefaultStopPolicy", "setup"]
