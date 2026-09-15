"""think.history_assemble — typed-boundary adapter for RunSessionWriter.

The graph node registered as ``think::history.derive`` is produced by the
:func:`@graph_node <graph_node>` decorator (ADR-0227) applied to the pure
``history_assemble`` async fn in
:mod:`lca.framework.graph.nodes.history_assemble`. The decorator carries the
``NodeExecutor``-shaped dataclass + composite-key registration, so this
plugin module is a thin re-export.
"""

from lca.framework.graph.nodes.history_assemble import history_assemble

__all__ = ["history_assemble"]
