"""Subgraph framework layer — node + edge graph execution plugins.

Framework plugin collection: id prefix ``subgraph.*``. Maintains strict
separation from business plugin collection under :mod:`lca.plugins`
(id prefix ``phase.*`` / ``<capability_key>``).

Public re-exports for convenience:

- :class:`SubgraphRuntime` Protocol — capability resolution seam
"""

from lca.framework.subgraph.protocols import SubgraphRuntime

__all__ = ["SubgraphRuntime"]
