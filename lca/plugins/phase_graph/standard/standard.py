# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.standard.standard,
#        to: lca.plugins.loop.graph.topology.standard.plugin,
#        delete_when: rg 'phase_graph\.standard' lca/ tests/ bundles/ = 0,
#        forbidden_new_usage: true)
"""Legacy re-export; SSOT is ``lca.plugins.loop.graph.topology.standard.plugin``."""

from lca.plugins.loop.graph.topology.standard.plugin import (
    Config,
    PhaseNodeConfig,
    SPEC,
    setup,
)

__all__ = ["Config", "PhaseNodeConfig", "SPEC", "setup"]
