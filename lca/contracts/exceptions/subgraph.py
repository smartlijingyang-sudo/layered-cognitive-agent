"""Subgraph recursion exception family (ADR-0217 §3.3.1, PG-006/PG-007-*).

Three closed-set failure modes for nested BundleGraphSpec v2 graphs:

- :class:`SubgraphDepthExceededError` — PG-007-depth: nesting depth > soft
  limit (``max_subgraph_depth``, default 8).
- :class:`SubgraphCycleError` — PG-007-cycle: same ``plan_ref`` appears
  twice on the recursion stack.
- :class:`PortNamingConflictError` — PG-006-port-conflict: two nodes in
  the same ``BundleGraphSpec`` declare the same output port.

All three carry identifying attributes (``depth``, ``plan_ref``,
``node_id``, ``port``) so callers can introspect without re-parsing the
message string.

Dependency rule: stays in ``lca.contracts`` and imports nothing below
contracts layer (ADR-0015).
"""

from __future__ import annotations

__all__ = [
    "PortNamingConflictError",
    "SubgraphCycleError",
    "SubgraphDepthExceededError",
]


class SubgraphDepthExceededError(RuntimeError):
    """PG-007-depth: nesting depth > ``max_subgraph_depth`` (default 8)."""

    def __init__(self, depth: int, max_depth: int) -> None:
        super().__init__(
            f"subgraph depth {depth} exceeds max {max_depth}"
        )
        self.depth = depth
        self.max_depth = max_depth


class SubgraphCycleError(RuntimeError):
    """PG-007-cycle: same ``plan_ref`` appears twice on the recursion stack."""

    def __init__(self, plan_ref: str) -> None:
        super().__init__(f"subgraph cycle detected at plan_ref={plan_ref!r}")
        self.plan_ref = plan_ref


class PortNamingConflictError(ValueError):
    """PG-006-port-conflict: two nodes declare the same output port."""

    def __init__(self, node_id: str, port: str) -> None:
        super().__init__(f"port {port!r} conflict in node {node_id!r}")
        self.node_id = node_id
        self.port = port
