"""Stateful traversal bookkeeping for declarative phase-graph execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseEdge,
    PhaseInput,
    PhaseResult,
    PhaseRunCursor,
    SemanticPhase,
)


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
            next_input=input
            or PhaseInput(
                artifact=artifacts.get("payload"),
                causation_refs=cursor.causation_refs,
            ),
        )

    def visit(self, *, node_id: str, max_visits: int) -> int:
        """Record entry to a node and enforce its declared visit budget."""
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
        """Store the next-phase artifacts derived from a completed phase."""
        payload = result.payload if result.payload is not None else effect_output
        self.artifacts["result"] = result
        self.artifacts["payload"] = payload
        self.artifacts[semantic_phase.value] = payload
        return payload

    def advance(
        self,
        *,
        edge: PhaseEdge,
        payload: object | None,
        causation_refs: tuple[str, ...],
    ) -> None:
        """Advance over an edge, enforcing declared loop budgets."""
        key = (edge.source, edge.target)
        count = self.edge_counts.get(key, 0) + 1
        self.edge_counts[key] = count
        if edge.loop and count > edge.loop.max_iterations:
            raise DeclarativeValidationError(
                "PG-007", f"loop edge budget exhausted: {edge.source}->{edge.target}"
            )
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
