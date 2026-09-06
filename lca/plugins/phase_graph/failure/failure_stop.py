# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.failure.failure_stop,
#        to: lca.plugins.loop.phase._shared.failure_stop,
#        delete_when: rg 'phase_graph\.failure\.failure_stop' lca/ tests/ = 0,
#        forbidden_new_usage: true)
"""Legacy import path for ``phase_failure_stop_result``."""

from lca.plugins.loop.phase._shared.failure_stop import phase_failure_stop_result

__all__ = ["phase_failure_stop_result"]
