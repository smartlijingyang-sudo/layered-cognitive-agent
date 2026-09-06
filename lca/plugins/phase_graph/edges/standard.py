# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.edges_standard,
#        to: lca.plugins.loop.graph.edges.standard.plugin,
#        delete_when: rg 'phase_graph\.edges_standard' bundles/ = 0,
#        forbidden_new_usage: true)
"""Flat bundle $module shim for ``phase.edge.standard``."""

from lca.plugins.loop.graph.edges.standard.plugin import Config, SPEC, setup

__all__ = ["Config", "SPEC", "setup"]
