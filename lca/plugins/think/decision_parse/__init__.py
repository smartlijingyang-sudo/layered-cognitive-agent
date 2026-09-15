"""think.decision_parse — typed-boundary adapter for LLMResponse → Decision.

The graph node registered as ``think::decision.parse`` is produced by the
:func:`@graph_node <graph_node>` decorator (ADR-0227) applied to the pure
``decision_parse`` async fn in
:mod:`lca.framework.graph.nodes.decision_parse`. The decorator carries the
``NodeExecutor``-shaped dataclass + composite-key registration, so this
plugin module is a thin re-export.
"""

from lca.framework.graph.nodes.decision_parse import decision_parse

__all__ = ["decision_parse"]
