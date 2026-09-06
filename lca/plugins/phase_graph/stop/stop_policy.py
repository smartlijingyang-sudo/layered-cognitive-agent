# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.stop.stop_policy,
#        to: lca.plugins.phase_graph.stop.policy,
#        delete_when: rg 'phase_graph\.stop\.stop_policy' lca/ tests/ = 0,
#        forbidden_new_usage: true)
"""Nested import shim for ``DefaultStopPolicy``."""

from lca.plugins.phase_graph.stop.policy import Config, DefaultStopPolicy, setup

__all__ = ["Config", "DefaultStopPolicy", "setup"]
