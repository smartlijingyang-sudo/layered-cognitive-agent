# COMPAT(owner: ADR-0194, from: lca.plugins.phase_graph.aggregator,
#        to: lca.plugins.loop.graph.nodes.aggregator.plugin,
#        delete_when: rg 'phase_graph\.aggregator\b' lca/ tests/ bundles/ = 0,
#        forbidden_new_usage: true)
"""Legacy flat re-export; SSOT is ``lca.plugins.loop.graph.nodes.aggregator.plugin``."""

from lca.plugins.loop.graph.nodes.aggregator.plugin import (
    AggregatorGraphNodeExecutor,
    Config,
    setup,
)

__all__ = ["AggregatorGraphNodeExecutor", "Config", "setup"]
