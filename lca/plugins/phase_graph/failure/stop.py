# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.failure.stop,
#        to: lca.plugins.loop.phase._shared.failure_stop,
#        delete_when: rg 'phase_graph\.failure\.stop' lca/ tests/ = 0,
#        forbidden_new_usage: true)
"""Legacy re-export; SSOT is ``lca.plugins.loop.phase._shared.failure_stop``."""

from lca.plugins.loop.phase._shared.failure_stop import phase_failure_stop_result

__all__ = ["phase_failure_stop_result"]
