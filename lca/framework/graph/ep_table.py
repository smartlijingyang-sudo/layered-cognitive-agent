"""GraphEpTable — data-driven mapping from observation kind to EP name.

The table is the single point that decides which execution-point
name a given :class:`GraphObservation.kind` resolves to. Adding a
new EP type means adding a row to this table; the kernel and
observer do not change.

Why a table instead of an ``if/elif``:
- The kernel has five call sites, but a single table captures the
  full kind→EP rule so review and tests can scan it once.
- Profiles that want a different EP naming convention (e.g. a
  vendor observability backend with prefixed EPs) replace the
  table wholesale; nothing else changes.
- Tests can pin the table against the spine's EP whitelist to
  catch drift early.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lca.framework.graph.observation import (
    KIND_EDGE,
    KIND_SUBGRAPH_ENTER,
    KIND_SUBGRAPH_EXIT,
    KIND_VISIT_END,
    KIND_VISIT_START,
)

EP_NODE_START = "phase_graph.node.start"
EP_NODE_END = "phase_graph.node.end"
EP_EDGE_TRANSIT = "phase_graph.edge.transit"
EP_SUBGRAPH_ENTER = "phase_graph.subgraph.enter"
EP_SUBGRAPH_EXIT = "phase_graph.subgraph.exit"


@dataclass(frozen=True, slots=True)
class GraphEpTable:
    """kind → execution_point mapping. Frozen so callers cannot mutate."""

    visit_start: str = EP_NODE_START
    visit_end: str = EP_NODE_END
    edge: str = EP_EDGE_TRANSIT
    subgraph_enter: str = EP_SUBGRAPH_ENTER
    subgraph_exit: str = EP_SUBGRAPH_EXIT

    def resolve(self, kind: str) -> str:
        table: Mapping[str, str] = {
            KIND_VISIT_START: self.visit_start,
            KIND_VISIT_END: self.visit_end,
            KIND_EDGE: self.edge,
            KIND_SUBGRAPH_ENTER: self.subgraph_enter,
            KIND_SUBGRAPH_EXIT: self.subgraph_exit,
        }
        try:
            return table[kind]
        except KeyError as exc:
            raise KeyError(
                f"GraphEpTable has no entry for kind={kind!r}; available: {sorted(table)}"
            ) from exc

    def all(self) -> Mapping[str, str]:
        """Return every kind→EP mapping. Used by tests and audits."""
        return {
            KIND_VISIT_START: self.visit_start,
            KIND_VISIT_END: self.visit_end,
            KIND_EDGE: self.edge,
            KIND_SUBGRAPH_ENTER: self.subgraph_enter,
            KIND_SUBGRAPH_EXIT: self.subgraph_exit,
        }


_DEFAULT_EP_TABLE = GraphEpTable()


def default_graph_ep_table() -> GraphEpTable:
    """Return the production EP table. Frozen; safe to share."""
    return _DEFAULT_EP_TABLE


__all__ = [
    "EP_EDGE_TRANSIT",
    "EP_NODE_END",
    "EP_NODE_START",
    "EP_SUBGRAPH_ENTER",
    "EP_SUBGRAPH_EXIT",
    "GraphEpTable",
    "default_graph_ep_table",
]
