"""Contract coverage for passive phase progress publication in the Agent Loop."""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseInput, PhaseResult, SemanticPhase
from lca.contracts.protocols.runtime.runtime_lifecycle import (
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
)
from lca.harness.declarative import GenericPlanInterpreter, GraphAssembler, MappingRestrictedScope
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from tests.phase_executors import standard_phase_executors


@dataclass
class _RecordingPublisher:
    events: list[RuntimeLifecycleEvent]

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        self.events.append(event)


class _FailingPerceiveExecutor:
    async def execute(self, context: object, input: PhaseInput) -> PhaseResult:
        del context, input
        raise RuntimeError("perceive executor unavailable")


class _AllowContribution:
    async def execute(self, context: object, input: PhaseInput) -> PhaseResult:
        del context, input
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                plugin_id="test.phase-lifecycle-contribution",
                kind=ControlVerdictKind.ALLOW,
            ),
        )


def _standard_plan():
    return compile_plan(resolve_profile("profiles/web-standard.yaml"))


def _raise_on_perceive_exhaustion(plan):
    assert plan.phase_graph is not None
    nodes = tuple(
        replace(
            node,
            execution_policy=replace(node.execution_policy, on_exhausted="raise"),
        )
        if node.id == "perceive.main"
        else node
        for node in plan.phase_graph.nodes
    )
    return replace(plan, phase_graph=replace(plan.phase_graph, nodes=nodes))


def _capabilities(plan) -> dict[str, object]:
    capabilities = dict(standard_phase_executors())
    allow = _AllowContribution()
    for binding in plan.phase_bindings:
        for contribution in binding.contributions:
            capabilities[contribution.executor] = allow
    return capabilities


def _executable(plan, capabilities: dict[str, object] | None = None):
    return GraphAssembler().assemble(
        plan, MappingRestrictedScope(capabilities or _capabilities(plan))
    )


@pytest.mark.asyncio
async def test_phase_events_publish_ordered_safe_progress_for_every_semantic_phase() -> None:
    plan = _standard_plan()
    events: list[RuntimeLifecycleEvent] = []
    interpreter = GenericPlanInterpreter(lifecycle_publisher=_RecordingPublisher(events))

    result = await interpreter.run(_executable(plan), state={"immutable": True})

    assert [visit.semantic_phase for visit in result.visits] == list(SemanticPhase)
    assert [event.type for event in events] == [
        event_type
        for _phase in SemanticPhase
        for event_type in (
            RuntimeLifecycleEventType.PHASE_STARTED,
            RuntimeLifecycleEventType.PHASE_COMPLETED,
        )
    ]
    assert [event.semantic_phase for event in events[::2]] == [
        phase.value for phase in SemanticPhase
    ]
    assert [event.semantic_phase for event in events[1::2]] == [
        phase.value for phase in SemanticPhase
    ]
    assert [event.phase_cursor for event in events[::2]] == [
        binding.node_id for binding in plan.phase_bindings
    ]
    assert [event.phase_cursor for event in events[1::2]] == [
        binding.node_id for binding in plan.phase_bindings
    ]
    assert all(event.result_kind is None for event in events[::2])
    assert all(event.result_kind for event in events[1::2])
    assert all(event.trace_id == "" for event in events)
    assert all(event.status.value == "working" for event in events)
    assert all(event.budget.max_steps is None for event in events)
    assert {
        "task",
        "state",
        "artifacts",
        "prompt",
        "tool_arguments",
        "payload",
        "error",
    }.isdisjoint(RuntimeLifecycleEvent.__dataclass_fields__)


@pytest.mark.asyncio
async def test_phase_executor_failure_publishes_failed_without_a_completion_event() -> None:
    plan = _raise_on_perceive_exhaustion(_standard_plan())
    events: list[RuntimeLifecycleEvent] = []
    capabilities = _capabilities(plan)
    capabilities["phase.perceive.standard"] = _FailingPerceiveExecutor()
    interpreter = GenericPlanInterpreter(lifecycle_publisher=_RecordingPublisher(events))

    result = await interpreter.run(_executable(plan, capabilities), state={"immutable": True})

    assert result.outcome is not None
    assert result.outcome.kind == "failed"
    assert [event.type for event in events] == [
        RuntimeLifecycleEventType.PHASE_STARTED,
        RuntimeLifecycleEventType.PHASE_FAILED,
    ]
    assert [event.semantic_phase for event in events] == [
        SemanticPhase.PERCEIVE.value,
        SemanticPhase.PERCEIVE.value,
    ]
    assert [event.phase_cursor for event in events] == ["perceive.main", "perceive.main"]
    assert all(event.result_kind is None for event in events)
