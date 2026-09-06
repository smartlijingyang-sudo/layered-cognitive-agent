# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.recovery.recovery,
#        to: lca.plugins.loop.graph.recovery.plugin,
#        delete_when: rg 'phase_graph\.recovery' lca/ tests/ bundles/ = 0,
#        forbidden_new_usage: true)
"""Legacy re-export; SSOT is ``lca.plugins.loop.graph.recovery.plugin``."""

from lca.plugins.loop.graph.recovery.plugin import (
    RecoveryEdgeConfig,
    RecoveryLoopConfig,
    SPEC,
    setup,
)

__all__ = ["RecoveryEdgeConfig", "RecoveryLoopConfig", "SPEC", "setup"]
