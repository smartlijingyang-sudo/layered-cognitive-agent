# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.resilient.resilient,
#        to: lca.plugins.loop.graph.resilient.plugin,
#        delete_when: rg 'phase_graph\.resilient' lca/ tests/ bundles/ = 0,
#        forbidden_new_usage: true)
"""Legacy re-export; SSOT is ``lca.plugins.loop.graph.resilient.plugin``."""

from lca.plugins.loop.graph.resilient.plugin import (
    Config,
    PhaseAttemptPolicyConfig,
    SPEC,
    setup,
)

__all__ = ["Config", "PhaseAttemptPolicyConfig", "SPEC", "setup"]
