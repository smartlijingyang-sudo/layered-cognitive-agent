"""Stateful traversal bookkeeping for declarative phase-graph execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseEdge,
    PhaseInput,
    PhaseResult,
    PhaseRunCursor,
    SemanticPhase,
)

if TYPE_CHECKING:
    from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
        PhaseNode,
    )


# ``PhaseTraversal`` is defined later in this same module. Use string form so
# the annotation resolves at runtime under ``from __future__ import annotations``
# without requiring forward-reference bookkeeping inside ``TYPE_CHECKING``.
PredicateRegistry = Callable[[str], Callable[["PhaseTraversal"], bool] | None]


@dataclass(slots=True)
class PhaseTraversal:
    """Own mutable graph traversal state and produce durable phase cursors.

    The interpreter owns execution semantics.  This module owns the visit and
    edge budgets, carried artifacts, next input, and cursor construction shared
    by completed, paused, failed, and governed outcomes.
    """

    plan_ref: str
    current_node_id: str
    visit_counts: dict[str, int]
    edge_counts: dict[tuple[str, str], int]
    artifacts: dict[str, object]
    # ADR-0219 §4: typed mirror of the legacy ``artifacts`` dict. Each
    # completed phase's ``PhaseResult`` is keyed by ``SemanticPhase`` so
    # downstream ``context.payload_of(phase, T)`` calls don't need to
    # touch the string-keyed ``artifacts`` cache.
    results_by_phase: dict[SemanticPhase, PhaseResult]
    next_input: PhaseInput

    @classmethod
    def start(
        cls,
        *,
        plan_ref: str,
        entry_node_id: str,
        artifacts: Mapping[str, object] | None,
        input: PhaseInput | None,
    ) -> PhaseTraversal:
        """Create traversal state for a fresh plan execution."""
        return cls(
            plan_ref=plan_ref,
            current_node_id=entry_node_id,
            visit_counts={},
            edge_counts={},
            artifacts=dict(artifacts or {}),
            results_by_phase={},
            next_input=input or PhaseInput(),
        )

    @classmethod
    def resume(cls, *, cursor: PhaseRunCursor, input: PhaseInput | None) -> PhaseTraversal:
        """Restore traversal state from a durable phase cursor."""
        artifacts = dict(cursor.artifacts)
        return cls(
            plan_ref=cursor.plan_ref,
            current_node_id=cursor.node_id,
            visit_counts=dict(cursor.visit_counts),
            edge_counts={(source, target): count for source, target, count in cursor.edge_counts},
            artifacts=artifacts,
            # ADR-0219 §4: typed mirror is rebuilt on first ``record_result``
            # after resume; legacy ``artifacts`` string keys are kept for
            # forward-compat with cursors persisted before this change.
            results_by_phase={},
            next_input=input
            or PhaseInput(
                artifact=artifacts.get("payload"),
                causation_refs=cursor.causation_refs,
            ),
        )

    def visit(
        self,
        *,
        node_id: str,
        max_visits: int,
        precondition: Callable[[PhaseTraversal], bool] | None = None,
    ) -> int:
        """Record entry to a node and enforce its declared visit budget.

        PR-C (ADR-0214 §6.2): when ``precondition`` is provided and evaluates
        ``False``, the visit is **not** recorded (so the call can be retried
        until ``max_visits`` is reached without exhausting the budget on
        unsatisfied preconditions) and ``-1`` is returned to signal
        "attempted but not entered". Callers / the interpreter are free to
        retry the visit on a subsequent iteration; when ``precondition`` is
        ``None`` (the default) the historical budget-only behaviour is
        preserved unchanged.
        """
        if precondition is not None and not precondition(self):
            return -1
        self.current_node_id = node_id
        count = self.visit_counts.get(node_id, 0) + 1
        self.visit_counts[node_id] = count
        if count > max_visits:
            raise DeclarativeValidationError("PG-007", f"node visit budget exhausted: {node_id}")
        return count

    def record_result(
        self,
        *,
        semantic_phase: SemanticPhase,
        result: PhaseResult,
        effect_output: object | None,
    ) -> object | None:
        """Store the next-phase artifacts derived from a completed phase.

        ADR-0219 §4: writes both the legacy string-keyed ``artifacts`` cache
        (for cursor persistence compatibility) and the typed
        ``results_by_phase`` mirror used by ``RestrictedPhaseContext``.

        When the phase executor chose to ship its typed result through
        ``command_envelope`` (effect.gateway path, e.g. act phase) the
        :class:`PhaseResult.payload` is ``None`` — the actual outcome
        lives on ``effect_output``. Mirror it onto ``result.payload`` so
        ``RestrictedPhaseContext.payload_of(phase, T)`` can read the
        downstream phase's typed artifact.
        """
        payload = result.payload if result.payload is not None else effect_output
        self.artifacts["result"] = result
        self.artifacts["payload"] = payload
        self.artifacts[semantic_phase.value] = payload
        # When the executor chose the effect path, ``result.payload`` is
        # ``None`` but the typed artifact is on ``effect_output``. Patch it
        # onto the recorded PhaseResult so the typed mirror exposes it.
        if result.payload is None and effect_output is not None:
            self.results_by_phase[semantic_phase] = replace(
                result, payload=effect_output
            )
        else:
            self.results_by_phase[semantic_phase] = result
        return payload

    def advance(
        self,
        *,
        edge: PhaseEdge,
        payload: object | None,
        causation_refs: tuple[str, ...],
        target_node: PhaseNode | None = None,
        predicate_registry: PredicateRegistry | None = None,
        on_terminal: Callable[[], None] | None = None,
    ) -> None:
        """Advance over an edge, enforcing declared loop budgets.

        PR-C (ADR-0214 §6.2): when ``target_node.terminal_predicate`` is
        declared and the named predicate evaluates ``True`` against the
        current traversal artifact state, ``on_terminal`` is invoked **in
        place of** advancing — the caller typically routes to ``stop.main``
        from that hook. When ``target_node`` / ``predicate_registry`` are
        omitted, the historical edge-budget-only behaviour is preserved
        unchanged (backward compatible).
        """
        key = (edge.source, edge.target)
        count = self.edge_counts.get(key, 0) + 1
        self.edge_counts[key] = count
        if edge.loop and count > edge.loop.max_iterations:
            raise DeclarativeValidationError(
                "PG-007", f"loop edge budget exhausted: {edge.source}->{edge.target}"
            )
        if (
            target_node is not None
            and target_node.terminal_predicate is not None
            and predicate_registry is not None
        ):
            predicate = predicate_registry(target_node.terminal_predicate)
            if predicate is None:
                raise DeclarativeValidationError(
                    "PG-007",
                    f"terminal predicate not registered: {target_node.terminal_predicate!r} "
                    f"(node {target_node.id})",
                )
            if predicate(self):
                if on_terminal is not None:
                    on_terminal()
                return
        self.current_node_id = edge.target
        self.next_input = PhaseInput(artifact=payload, causation_refs=causation_refs)

    def checkpoint(
        self,
        *,
        node_id: str | None = None,
        causation_refs: tuple[str, ...] = (),
        state_step: int = 0,
    ) -> PhaseRunCursor:
        """Capture all replay-relevant traversal state in one durable cursor."""
        return PhaseRunCursor(
            plan_ref=self.plan_ref,
            node_id=node_id or self.current_node_id,
            visit_counts=tuple(sorted(self.visit_counts.items())),
            edge_counts=tuple(
                (source, target, count)
                for (source, target), count in sorted(self.edge_counts.items())
            ),
            artifacts=dict(self.artifacts),
            causation_refs=causation_refs,
            budget_snapshot={"step": state_step},
        )

    def reset_visit(self, node_id: str) -> None:
        """Clear a node count when resume intentionally re-enters that node."""
        self.visit_counts.pop(node_id, None)


__all__ = ["PhaseTraversal"]
