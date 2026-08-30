"""Default policy interpreter for the declarative ``LoopGuard`` DSL.

This module is deliberately small and side-effect free.  It evaluates a
profile-provided edge guard after the edge's normal predicate has matched and
before graph traversal commits the re-entry.  It never mutates the state or
changes the graph; policy replacement happens through ``LoopGuardEvaluator``.
"""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_execution import PhaseResult
from lca.contracts.protocols.declarative.declarative_graph import LoopGuard, PhaseEdge
from lca.contracts.protocols.gate.loop_guard import LoopGuardEvaluator, LoopGuardVerdict
from lca.harness.declarative.graph.predicate import evaluate_restricted_predicate


class DeclarativeLoopGuardEvaluator(LoopGuardEvaluator):
    """Evaluate terminal predicates and named run-budget limits for loop edges."""

    def evaluate(
        self,
        *,
        guard: LoopGuard,
        edge: PhaseEdge,
        state: AgentState,
        result: PhaseResult,
        artifacts: Mapping[str, object],
    ) -> LoopGuardVerdict:
        """Allow re-entry only when the guard's terminal and budget checks permit it."""

        del edge
        predicate_artifacts = dict(artifacts)
        predicate_artifacts["budget"] = state.budget
        if evaluate_restricted_predicate(
            guard.terminal_predicate,
            result=result,
            artifacts=predicate_artifacts,
        ):
            return LoopGuardVerdict(allow=False, reason="terminal_predicate")
        if _budget_exhausted(guard.budget, state.budget):
            return LoopGuardVerdict(allow=False, reason=f"budget_exhausted:{guard.budget}")
        return LoopGuardVerdict(allow=True)


def _budget_exhausted(budget_name: str, budget: Budget) -> bool:
    """Evaluate an explicit, portable LoopGuard budget name.

    Unknown names remain valid opaque policy labels.  This preserves existing
    third-party topology plugins while allowing the built-in ``run.*`` names to
    enforce the same resource ledger used by the runtime.
    """

    checks = {
        "run.steps": _reached(budget.used_steps, budget.max_steps),
        "run.tokens": _reached(budget.used_tokens, budget.max_tokens),
        "run.cost_usd": _reached(budget.used_cost_usd, budget.max_cost_usd),
        "run.wall_clock_seconds": _wall_clock_reached(budget),
    }
    return checks.get(budget_name, False)


def _reached(used: int | float, maximum: int | float | None) -> bool:
    """Return whether consumption reached a configured hard upper limit."""

    return maximum is not None and used >= maximum


def _wall_clock_reached(budget: Budget) -> bool:
    """Use the Budget's canonical clock calculation for a wall-clock guard."""

    return bool(budget.exceeded("wall_clock_seconds"))


__all__ = ["DeclarativeLoopGuardEvaluator"]
