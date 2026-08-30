"""Behavioral tests for declarative loop-guard policy and its plugin seam."""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.declarative_phase_graph import LoopGuard, PhaseEdge, PhaseResult
from lca.contracts.protocols.loop_guard import LoopGuardVerdict
from lca.harness.declarative import GenericPlanInterpreter
from lca.harness.declarative.loop_guard import DeclarativeLoopGuardEvaluator


def _state(*, budget: Budget | None = None) -> AgentState:
    return AgentState(trace_id="trace-1", task="exercise loop guard", budget=budget or Budget())


def _guard(*, budget: str = "run.steps", terminal_predicate: str = "false") -> LoopGuard:
    return LoopGuard(
        max_iterations=3,
        budget=budget,
        terminal_predicate=terminal_predicate,
    )


def _edge(guard: LoopGuard) -> PhaseEdge:
    return PhaseEdge(source="stop.main", target="perceive.main", when="true", loop=guard)


def test_default_loop_guard_blocks_declared_terminal_predicate() -> None:
    evaluator = DeclarativeLoopGuardEvaluator()
    guard = _guard(terminal_predicate="result.next_hints.finished")

    verdict = evaluator.evaluate(
        guard=guard,
        edge=_edge(guard),
        state=_state(),
        result=PhaseResult(result_kind="stop_decision", next_hints={"finished": True}),
        artifacts={},
    )

    assert verdict == LoopGuardVerdict(allow=False, reason="terminal_predicate")


def test_default_loop_guard_blocks_reentry_when_named_budget_is_exhausted() -> None:
    evaluator = DeclarativeLoopGuardEvaluator()
    guard = _guard(budget="run.tokens")

    verdict = evaluator.evaluate(
        guard=guard,
        edge=_edge(guard),
        state=_state(budget=Budget(max_tokens=12, used_tokens=12)),
        result=PhaseResult(result_kind="stop_decision"),
        artifacts={},
    )

    assert verdict == LoopGuardVerdict(allow=False, reason="budget_exhausted:run.tokens")


def test_default_loop_guard_exposes_budget_to_terminal_predicate() -> None:
    evaluator = DeclarativeLoopGuardEvaluator()
    guard = _guard(terminal_predicate="budget.used_cost_usd >= budget.max_cost_usd")

    verdict = evaluator.evaluate(
        guard=guard,
        edge=_edge(guard),
        state=_state(budget=Budget(max_cost_usd=1.5, used_cost_usd=1.5)),
        result=PhaseResult(result_kind="stop_decision"),
        artifacts={},
    )

    assert verdict == LoopGuardVerdict(allow=False, reason="terminal_predicate")


def test_interpreter_skips_denied_loop_edge_and_uses_declared_fallback() -> None:
    class DenyReentry:
        def evaluate(self, **_kwargs: object) -> LoopGuardVerdict:
            return LoopGuardVerdict(allow=False, reason="profile_policy")

    guard = _guard()
    loop = _edge(guard)
    fallback = PhaseEdge(source="stop.main", target="finalize.main", when="true")
    selected = GenericPlanInterpreter(loop_guard_evaluator=DenyReentry())._select_edge(
        (loop, fallback),
        "stop.main",
        PhaseResult(result_kind="stop_decision"),
        {},
        _state(),
    )

    assert selected == fallback


def test_budget_reports_overage_for_all_runtime_resources() -> None:
    assert Budget(max_steps=4, used_steps=5).exceeded("steps")
    assert Budget(max_tokens=5, used_tokens=6).exceeded("tokens")
    assert Budget(max_cost_usd=0.25, used_cost_usd=0.26).exceeded("cost_usd")
    assert not Budget(max_steps=4, used_steps=4).exceeded()
