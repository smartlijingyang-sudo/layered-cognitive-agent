"""think.llm_dispatch — typed-boundary adapter for LLM call + persist-before-execute.

The graph node registered as ``think::llm.call`` is produced by the
:func:`@graph_node <graph_node>` decorator (ADR-0227) applied to the pure
``llm_dispatch`` async fn in
:mod:`lca.framework.graph.nodes.llm_dispatch`. The decorator carries the
``NodeExecutor``-shaped dataclass + composite-key registration, so this
plugin module is a thin re-export.
"""

from lca.framework.graph.nodes.llm_dispatch import llm_dispatch

__all__ = ["llm_dispatch"]
