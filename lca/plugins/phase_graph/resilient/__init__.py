# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.resilient,
#        to: lca.plugins.loop.graph.resilient.plugin,
#        delete_when: rg 'phase_graph\.resilient[^.]' bundles/ = 0,
#        forbidden_new_usage: true)
"""Bundle $module shim for ``phase.execution_policy.resilient``."""

from lca.plugins.loop.graph.resilient.plugin import (
    Config,
    PhaseAttemptPolicyConfig,
    SPEC,
    setup,
)

__all__ = ["Config", "PhaseAttemptPolicyConfig", "SPEC", "setup"]
