# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.recovery,
#        to: lca.plugins.loop.graph.recovery.plugin,
#        delete_when: rg 'phase_graph\.recovery[^.]' bundles/ = 0,
#        forbidden_new_usage: true)
"""Bundle $module shim for ``phase.edge.reflect_to_think.recovery``."""

from lca.plugins.loop.graph.recovery.plugin import (
    RecoveryEdgeConfig,
    RecoveryLoopConfig,
    SPEC,
    setup,
)

__all__ = ["RecoveryEdgeConfig", "RecoveryLoopConfig", "SPEC", "setup"]
