"""Regression coverage for plan-declared phase attempt fault tolerance."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import timedelta

import pytest

from lca.contracts.atoms.ids import utc_now
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.stop import StopReason
from lca.contracts.protocols.act.command_envelope import RunFact
from lca.contracts.protocols.declarative.declarative_execution import (
    ExecutionOutcome,
    PhaseExecutionFailure,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_fault_tolerance import PhaseExecutionPolicy
from lca.contracts.protocols.declarative.declarative_phase_graph import SemanticPhase
from lca.harness.declarative import GenericPlanInterpreter, GraphAssembler, MappingRestrictedScope
from lca.harness.declarative.compile.assembler import ExecutableNode
from lca.harness.declarative.compile.phase_execution_policy import (
    PhaseExecutionExhaustedError,
    RunDeadlineExceededError,
    _phase_error_message,
)
from lca.harness.declarative.controls.validation import PhaseGraphValidator, validation_errors
from lca.harness.declarative.graph.traversal import PhaseTraversal
from lca.harness.declarative.lifecycle.phase_observation import NullPhaseObserver
from lca.harness.declarative.lifecycle.phase_transaction import PhaseExecutionTransaction
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from tests.phase_executors import standard_phase_executors


@dataclass
class _Journal:
    facts: list[RunFact] = field(default_factory=list)

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str:
        self.facts.append(fact)
        return fact.fact_id

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        return evidence_ref

    def commit_observation(self, observation: object, *, plan_ref: str, node_ref: str) -> str:
        return f"{node_ref}:observation"


class _FlakyExecutor:
    def __init__(self, failures: int) -> None:
        self._failures_remaining = failures
        self.calls = 0

    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        self.calls += 1
        if self._failures_remaining:
            self._failures_remaining -= 1
            raise ConnectionError("transient dependency unavailable")
        return PhaseResult(result_kind="context", payload="recovered")


class _SlowExecutor:
    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        await asyncio.sleep(0.05)
        return PhaseResult(result_kind="context", payload="too late")


class _PassthroughReducer:
    def apply_delta(self, state: AgentState, _delta: object) -> AgentState:
        return state


def _transaction_run(
    executor: object,
    policy: PhaseExecutionPolicy,
    *,
    budget: Budget | None = None,
):
    journal = _Journal()
    run_budget = budget or Budget()
    transaction = PhaseExecutionTransaction(
        journal=journal,
        effect_gateway=None,
        reducer=None,
        phase_observer=NullPhaseObserver(),
    )
    node = ExecutableNode(
        node_id="perceive.main",
        semantic_phase=SemanticPhase.PERCEIVE,
        executor_capability="phase.perceive.fixture",
        executor=executor,  # type: ignore[arg-type]
        contributions=(),
        execution_policy=policy,
    )
    traversal = PhaseTraversal.start(
        plan_ref="test-plan",
        entry_node_id=node.node_id,
        artifacts=None,
        input=None,
    )
    return transaction.run(
        node_id=node.node_id,
        semantic_phase=node.semantic_phase,
        executable_node=node,
        state=AgentState(trace_id="trace", task="task", budget=run_budget),
        budget=run_budget,
        plan_ref="test-plan",
        traversal=traversal,
        visit_count=1,
        capabilities={},
        effect_policy=None,
    ), journal


@pytest.mark.asyncio
async def test_transient_phase_error_is_retried_under_declared_policy() -> None:
    executor = _FlakyExecutor(failures=1)
    result_awaitable, journal = _transaction_run(
        executor,
        PhaseExecutionPolicy(
            max_attempts=2,
            retry_on=("transient",),
            on_exhausted="route_to_stop",
        ),
    )

    result = await result_awaitable

    assert executor.calls == 2
    assert result.result.payload == "recovered"
    assert [fact.kind for fact in journal.facts] == ["phase.result"]


@pytest.mark.asyncio
async def test_timeout_exhaustion_becomes_a_typed_and_auditable_phase_error() -> None:
    result_awaitable, journal = _transaction_run(
        _SlowExecutor(),
        PhaseExecutionPolicy(
            max_attempts=2,
            timeout_seconds=0.001,
            retry_on=("timeout",),
            on_exhausted="route_to_stop",
        ),
    )

    result = await result_awaitable

    assert result.result.result_kind == "phase_error"
    assert isinstance(result.effective_payload, PhaseExecutionFailure)
    assert len(result.effective_payload.attempts) == 2
    assert result.effective_payload.attempts[-1].category == "timeout"
    assert [fact.kind for fact in journal.facts] == [
        "phase.result",
        "phase.execution_exhausted",
    ]
    failure_fact = journal.facts[-1]
    assert failure_fact.payload == {
        "node_id": "perceive.main",
        "attempts": (
            {
                "attempt": 1,
                "category": "timeout",
                "error_type": "TimeoutError",
                "error_message": "",
            },
            {
                "attempt": 2,
                "category": "timeout",
                "error_type": "TimeoutError",
                "error_message": "",
            },
        ),
        "final_category": "timeout",
        "last_tool_call_id": None,  # ADR-0162: phase execution failure carries last_tool_call_id
    }


@pytest.mark.asyncio
async def test_run_deadline_prevents_executor_start_after_budget_is_exhausted() -> None:
    executor = _FlakyExecutor(failures=0)
    result_awaitable, journal = _transaction_run(
        executor,
        PhaseExecutionPolicy(max_attempts=1, on_exhausted="route_to_stop"),
        budget=Budget(
            max_wall_clock_seconds=1,
            started_at=utc_now() - timedelta(seconds=2),
        ),
    )

    result = await result_awaitable

    assert executor.calls == 0
    assert result.result.result_kind == "phase_error"
    assert isinstance(result.effective_payload, PhaseExecutionFailure)
    failure = result.effective_payload.attempts[-1]
    assert failure.category == "timeout"
    assert failure.error_type == RunDeadlineExceededError.__name__
    assert [fact.kind for fact in journal.facts] == [
        "phase.result",
        "phase.execution_exhausted",
    ]


@pytest.mark.asyncio
async def test_run_deadline_constrains_unbounded_phase_timeout() -> None:
    result_awaitable, _journal = _transaction_run(
        _SlowExecutor(),
        PhaseExecutionPolicy(max_attempts=1, on_exhausted="route_to_stop"),
        budget=Budget(max_wall_clock_seconds=10, started_at=utc_now() - timedelta(seconds=9.98)),
    )

    result = await result_awaitable

    assert result.result.result_kind == "phase_error"
    assert isinstance(result.effective_payload, PhaseExecutionFailure)
    assert result.effective_payload.attempts[-1].category == "timeout"


@pytest.mark.asyncio
async def test_retry_backoff_never_sleeps_past_run_deadline() -> None:
    executor = _FlakyExecutor(failures=1)
    result_awaitable, _journal = _transaction_run(
        executor,
        PhaseExecutionPolicy(
            max_attempts=2,
            retry_on=("transient",),
            initial_backoff_seconds=1,
            on_exhausted="route_to_stop",
        ),
        budget=Budget(max_wall_clock_seconds=10, started_at=utc_now() - timedelta(seconds=9.9)),
    )

    result = await result_awaitable

    assert executor.calls == 1
    assert isinstance(result.effective_payload, PhaseExecutionFailure)
    assert [failure.category for failure in result.effective_payload.attempts] == [
        "transient",
        "timeout",
    ]
    assert result.effective_payload.attempts[-1].error_type == RunDeadlineExceededError.__name__


@pytest.mark.asyncio
async def test_terminal_phase_policy_remains_fail_closed_when_configured_to_raise() -> None:
    result_awaitable, _journal = _transaction_run(
        _FlakyExecutor(failures=1),
        PhaseExecutionPolicy(max_attempts=1, on_exhausted="raise"),
    )

    with pytest.raises(PhaseExecutionExhaustedError) as error:
        await result_awaitable

    assert error.value.failure.attempts[-1].category == "transient"


@pytest.mark.asyncio
async def test_attempt_failure_captures_upstream_error_message() -> None:
    """捕获点的上游错误原文进入 PhaseAttemptFailure,供展示链投影。"""
    result_awaitable, _journal = _transaction_run(
        _FlakyExecutor(failures=1),
        PhaseExecutionPolicy(max_attempts=1, on_exhausted="route_to_stop"),
    )

    result = await result_awaitable

    assert isinstance(result.effective_payload, PhaseExecutionFailure)
    attempt = result.effective_payload.attempts[-1]
    assert attempt.error_type == "ConnectionError"
    assert attempt.error_message == "transient dependency unavailable"


def test_phase_error_message_is_single_line_and_bounded() -> None:
    """归一化:空白折叠为单行;超过上限截断并带省略号。"""
    assert _phase_error_message(ValueError("first\nsecond\tthird")) == "first second third"

    capped = _phase_error_message(ValueError("x" * 600))
    assert capped.endswith("…")
    assert len(capped) <= len("x" * 600)
    assert capped[:-1] == "x" * 512


@pytest.mark.asyncio
async def test_default_graph_routes_retry_exhaustion_to_stop_without_runtime_branching() -> None:
    plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
    assert plan.phase_graph is not None
    graph = replace(
        plan.phase_graph,
        nodes=tuple(
            replace(
                node,
                execution_policy=replace(
                    node.execution_policy,
                    max_attempts=1,
                    initial_backoff_seconds=0,
                ),
            )
            if node.id == "perceive.main"
            else node
            for node in plan.phase_graph.nodes
        ),
    )
    plan = replace(plan, phase_graph=graph)
    capabilities: dict[str, object] = dict(standard_phase_executors())
    capabilities["phase.perceive.standard"] = _FlakyExecutor(failures=1)
    allow = _AllowContribution()
    for binding in plan.phase_bindings:
        for contribution in binding.contributions:
            capabilities[contribution.executor] = allow
    executable = GraphAssembler().assemble(plan, MappingRestrictedScope(capabilities))

    result = await GenericPlanInterpreter(reducer=_PassthroughReducer()).run(
        executable,
        state=AgentState(trace_id="trace", task="task", budget=Budget()),
        capabilities={},
    )

    assert [visit.node_id for visit in result.visits] == ["perceive.main", "stop.main"]
    assert result.outcome is not None
    assert result.outcome.kind is ExecutionOutcome.COMPLETED
    assert result.outcome.stop.reason is StopReason.ERROR
    assert result.outcome.stop.status is TaskStatus.FAILED


class _AllowContribution:
    async def execute(self, _context: object, _input: PhaseInput) -> PhaseResult:
        from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind

        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(plugin_id="test.allow", kind=ControlVerdictKind.ALLOW),
        )


def test_route_to_stop_policy_is_rejected_when_its_error_edge_is_missing() -> None:
    plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
    assert plan.phase_graph is not None
    graph = replace(
        plan.phase_graph,
        edges=tuple(
            edge
            for edge in plan.phase_graph.edges
            if not (
                edge.source == "perceive.main"
                and edge.when == 'result.result_kind == "phase_error"'
            )
        ),
    )

    report = PhaseGraphValidator().validate(
        graph,
        plan.phase_bindings,
        plan.plugin_specs,
        plan.effect_policy,
    )

    assert any(
        issue.code == "PG-010" and issue.location == "perceive.main"
        for issue in validation_errors(report)
    )


def test_standard_profile_compiles_plugin_declared_phase_execution_policies() -> None:
    plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
    assert plan.phase_graph is not None
    policies = {node.id: node.execution_policy for node in plan.phase_graph.nodes}

    assert policies["think.main"].max_attempts == 2
    assert policies["think.main"].timeout_seconds == 90.0
    assert policies["think.main"].retry_on == ("timeout", "transient")
    assert policies["act.main"].max_attempts == 1
    assert policies["act.main"].on_exhausted == "route_to_stop"
    assert policies["stop.main"].on_exhausted == "raise"
    error_edges = {
        edge.source
        for edge in plan.phase_graph.edges
        if edge.when == 'result.result_kind == "phase_error"'
    }
    assert error_edges == {
        "perceive.main",
        "think.main",
        "act.main",
        "reflect.main",
        "remember.main",
    }
