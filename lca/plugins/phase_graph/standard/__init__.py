# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.standard,
#        to: lca.plugins.loop.graph.topology.standard.plugin,
#        delete_when: rg 'phase_graph\.standard[^.]' bundles/ = 0,
#        forbidden_new_usage: true)
"""Bundle $module shim for ``phase.topology.standard``."""

from lca.plugins.loop.graph.topology.standard.plugin import (
    Config,
    PhaseNodeConfig,
    SPEC,
    setup,
)

__all__ = ["Config", "PhaseNodeConfig", "SPEC", "setup"]
