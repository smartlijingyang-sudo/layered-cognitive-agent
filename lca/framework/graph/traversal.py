"""PlanTraversal — typed state machine for one :class:`Plan` visit.

The traversal owns:

- which node the kernel should run next (``current``),
- which nodes have been visited and how often (for ``max_visits``),
- when the plan is terminated (no outgoing edges resolve to True).

It is a state machine, not a free-form iterator: ``terminated()`` is
the typed predicate the main loop checks, ``advance`` is the only way
to move forward, ``fork`` is the only way to recurse into a subgraph.

Replaces the legacy ``_loop_count > 20`` hard cap from
:class:`lca.framework.subgraph.plugins.node_graph_driver.NodeGraphDriver`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from lca.contracts.protocols.graph.plan import Plan, PlanEdge


@dataclass
class PlanTraversal:
    """State machine for one :class:`Plan` visit."""

    plan: Plan
    current_id: str = ""
    visit_counts: dict[str, int] = field(default_factory=dict)
    terminal: bool = False
    last_dispatch_kind: str = "init"
    terminal_reason: tuple[str, str, int, int] | None = None

    def __post_init__(self) -> None:
        if not self.current_id:
            for node in self.plan.nodes:
                if node.entry:
                    self.current_id = node.id
                    break
            if not self.current_id and self.plan.nodes:
                self.current_id = self.plan.nodes[0].id

    def visit(self, *, node_id: str, max_visits: int) -> int:
        """Record one visit to ``node_id``; return the new count.

        When the count exceeds ``max_visits`` the traversal is marked
        terminal (``terminal_reason`` is populated) instead of raising.
        The main loop in :class:`PlanInterpreter` checks ``terminated()``
        and exits cleanly — see ADR-0214 PG-007 passive→active.
        """
        if max_visits <= 0:
            raise ValueError(f"plan {self.plan.id!r} node {node_id!r}: max_visits must be > 0")
        self.visit_counts[node_id] = self.visit_counts.get(node_id, 0) + 1
        if self.visit_counts[node_id] > max_visits:
            self.terminal = True
            self.terminal_reason = (
                "budget_exceeded",
                node_id,
                max_visits,
                self.visit_counts[node_id],
            )
        return self.visit_counts[node_id]

    def terminated(self) -> bool:
        """True when the kernel should stop the loop."""
        return self.terminal

    def advance(
        self,
        *,
        edge: PlanEdge | None,
        dispatch_kind: str,
    ) -> None:
        """Move the cursor forward; ``edge=None`` means termination."""
        self.last_dispatch_kind = dispatch_kind
        if edge is None:
            self.terminal = True
            return
        self.current_id = edge.target

    def fork(self, *, entry: str) -> PlanTraversal:
        """Return a fresh traversal rooted at ``entry`` for subgraph recursion."""
        return PlanTraversal(plan=self.plan, current_id=entry)


def select_edge(
    *,
    edges: tuple[PlanEdge, ...],
    current_id: str,
    result: object | None = None,
    artifacts: Mapping[str, object] | None = None,
) -> PlanEdge | None:
    """Pick the first outgoing edge from ``current_id`` whose ``when`` evaluates true.

    The DSL evaluator is reused from the existing harness:
    :func:`lca.harness.graph.predicate.evaluate_restricted_predicate`.
    Tests inject a stub by replacing ``_PREDICATE_EVALUATOR``.
    """
    predicate = _PREDICATE_EVALUATOR
    for edge in edges:
        if edge.source != current_id:
            continue
        if predicate(edge.when, result=result, artifacts=artifacts or {}):
            return edge
    return None


_PREDICATE_EVALUATOR = None


def _default_predicate(
    when: str, *, result: object | None, artifacts: Mapping[str, object]
) -> bool:
    return when == "true" or when == ""


def install_predicate_evaluator(fn: object) -> None:
    """Replace the DSL evaluator. Used by host wiring; tests can stub."""
    global _PREDICATE_EVALUATOR
    _PREDICATE_EVALUATOR = fn  # type: ignore[assignment]


def _resolve_default_predicate() -> object:
    try:
        from lca.harness.graph.predicate import evaluate_restricted_predicate

        return evaluate_restricted_predicate
    except ImportError as exc:
        import logging

        logging.getLogger(__name__).warning(
            "predicate evaluator fallback to _default_predicate: %s; "
            "outer-plan edges with predicate expressions will misroute",
            exc,
        )
        return _default_predicate


install_predicate_evaluator(_resolve_default_predicate())


__all__ = [
    "PlanTraversal",
    "install_predicate_evaluator",
    "select_edge",
]
