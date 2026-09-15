"""PlanTraversal — typed state machine for one :class:`Plan` visit.

The traversal owns:

- which node the kernel should run next (``current``),
- which nodes have been visited and how often (for resume checkpoints),
- when the plan is terminated (no outgoing edges resolve to True).

It is a state machine, not a free-form iterator: ``terminated()`` is
the typed predicate the main loop checks, ``advance`` is the only way
to move forward, ``fork`` is the only way to recurse into a subgraph.

D4 cutover: ``select_edge`` now takes a ``reader_factory`` and evaluates
typed :class:`Predicate` objects via :func:`evaluate_predicate`. The
legacy string DSL evaluator has been deleted.

ADR-0225: per-node ``max_visits`` cap removed. ``visit_counts`` is
retained so the resume path can replay prior visits; the kernel no
longer flips ``terminal`` based on a per-node ceiling.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from lca.contracts.protocols.graph.errors import UnknownFieldError, UnsetPortError
from lca.contracts.protocols.graph.plan import Plan, PlanEdge
from lca.framework.graph.port_reader import PortReader
from lca.framework.graph.predicate_evaluator import evaluate_predicate


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

    def visit(self, *, node_id: str) -> int:
        """Record one visit to ``node_id``; return the new count.

        ADR-0225: the per-node ``max_visits`` cap has been deleted.
        ``visit_counts`` is still updated so the resume path can
        replay prior visits; the kernel no longer flips ``terminal``
        based on a per-node ceiling.
        """
        self.visit_counts[node_id] = self.visit_counts.get(node_id, 0) + 1
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


ReaderFactory = Callable[[str], PortReader]


def select_edge(
    *,
    edges: tuple[PlanEdge, ...],
    current_id: str,
    reader_factory: ReaderFactory,
) -> PlanEdge | None:
    """Pick the first outgoing edge whose typed predicate evaluates true.

    D4 cutover: ``reader_factory`` builds a :class:`PortReader` for the
    edge's source node. Predicates are structured :class:`Predicate`
    objects evaluated by :func:`evaluate_predicate`. No string DSL, no
    silent None, no fallback.

    When a predicate references an unset port, the edge does not match
    (returns False) — this preserves the "no edge → terminate" semantics
    without raising on every unset port reference.
    """
    for edge in edges:
        if edge.source != current_id:
            continue
        if edge.when is None:
            return edge
        reader = reader_factory(edge.source)
        try:
            if evaluate_predicate(edge.when, reader=reader):
                return edge
        except (UnsetPortError, UnknownFieldError):
            continue
    return None


__all__ = [
    "PlanTraversal",
    "ReaderFactory",
    "select_edge",
]
