"""Regression tests for CognitiveRuntime.resume memory capture (ADR-0246 PR-8 bugfix).

Tests that:
1. CognitiveRuntime.resume accesses memory capability via capabilities.get("memory"),
   never directly via _bindings.memory (which raises AttributeError on DeclarativeRuntimeBindings).
2. Memory capture is strictly fail-soft: exceptions in adapter or memory do not crash resume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, Observation, Turn
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget, StateSnapshot
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import PhaseRunCursor
from lca.contracts.protocols.runtime.runtime.lifecycle import (
    RuntimeLifecycleEvent,
)
from lca.contracts.protocols.session.resume.input import ResumeInput
from lca.runtime.loop.runtime_loop import CognitiveRuntime
from lca.runtime.support.checkpoint_resolution import DeclarativeCheckpoint
from lca.runtime.support.runtime_bindings import RuntimePhaseCapabilities


@dataclass
class _RecordingSubscriber:
    events: list[RuntimeLifecycleEvent] = field(default_factory=list)

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        self.events.append(event)


class _MockDriver:
    def __init__(self) -> None:
        self.resumed_checkpoints: list[DeclarativeCheckpoint] = []

    async def resume(self, checkpoint: DeclarativeCheckpoint) -> Result:
        self.resumed_checkpoints.append(checkpoint)
        return Result(
            trace_id="trace_test",
            status=TaskStatus.COMPLETED,
            final_state_ref="state_ref_resumed",
            total_steps=1,
            budget_used=Budget(),
            output="resumed_ok",
        )


class _DeclarativeBindingsWithoutMemoryAttribute:
    """Mimics DeclarativeRuntimeBindings: capabilities is present, memory attribute is NOT."""

    def __init__(self, capabilities: RuntimePhaseCapabilities) -> None:
        self.capabilities = capabilities
        self.hooks = MagicMock()
        self.hooks.trigger = AsyncMock()
        self.reducer = MagicMock()
        self.state_store = MagicMock()
        self.resume_input_adapter = MagicMock()
        self.lifecycle_publisher = _RecordingSubscriber()
        self.driver = _MockDriver()

    def plan_ref(self) -> str:
        return "plan://test-resume"

    def require_executable_plan(self) -> None:
        pass

    def new_driver(self) -> _MockDriver:
        return self.driver


def _create_cursor() -> PhaseRunCursor:
    return PhaseRunCursor(
        plan_ref="plan://test-resume",
        node_id="phase.think.fold",
        visit_counts=(),
        edge_counts=(),
        artifacts={},
        causation_refs=(),
        budget_snapshot={},
    )


def _create_snapshot_and_state():
    cursor = _create_cursor()
    state = AgentState(
        trace_id="trace_test",
        task="帮我选角色",
        budget=Budget(),
    )
    state.phase_cursor = cursor
    snapshot = StateSnapshot(
        snapshot_id="snap_0",
        step=1,
        state_ref="state_ref_0",
        trace_id="trace_test",  # type: ignore[arg-type]
        run_id="run_test",  # type: ignore[arg-type]
        phase_cursor=cursor,
    )
    return snapshot, state


def _create_resume_input(answer: str) -> ResumeInput:
    obs = Observation(
        observation_id="obs_resume_1",
        success=True,
        payload=answer,
        extra={"source": "human_answer", "tool_name": "askUserQuestion"},
    )
    decision = Decision(
        decision_id="dec_hitl_1",
        action_type=ActionType.ASK_HUMAN,
        rationale="HITL question",
        confidence=1.0,
    )
    return ResumeInput(
        input_value=answer,
        turn=Turn(decision=decision, observation=obs),
    )


@pytest.mark.asyncio
async def test_resume_with_declarative_bindings_does_not_raise_attribute_error() -> None:
    capabilities = RuntimePhaseCapabilities({})
    bindings = _DeclarativeBindingsWithoutMemoryAttribute(capabilities)
    # Ensure bindings does NOT have a memory attribute (like DeclarativeRuntimeBindings)
    assert not hasattr(bindings, "memory")

    runtime = CognitiveRuntime(bindings)  # type: ignore[arg-type]
    snapshot, state = _create_snapshot_and_state()
    bindings.state_store.load = AsyncMock(return_value=state)
    resume_input = _create_resume_input("我是架构师")
    bindings.resume_input_adapter.normalize = MagicMock(return_value=resume_input)
    bindings.reducer.apply_resume = MagicMock(return_value=state)

    # This MUST NOT crash with AttributeError: '...' object has no attribute 'memory'
    result = await runtime.resume(snapshot, input=resume_input)
    assert result.status is TaskStatus.COMPLETED
    assert len(bindings.driver.resumed_checkpoints) == 1


@pytest.mark.asyncio
async def test_resume_memory_capture_fail_soft_on_error() -> None:
    broken_adapter = MagicMock()
    broken_adapter.complete = AsyncMock(side_effect=RuntimeError("LLM failed"))
    broken_memory = MagicMock()
    broken_memory.update = AsyncMock(side_effect=RuntimeError("Memory disk failure"))

    capabilities = RuntimePhaseCapabilities(
        {
            "adapter": broken_adapter,
            "memory": broken_memory,
        }
    )
    bindings = _DeclarativeBindingsWithoutMemoryAttribute(capabilities)
    runtime = CognitiveRuntime(bindings)  # type: ignore[arg-type]

    snapshot, state = _create_snapshot_and_state()
    bindings.state_store.load = AsyncMock(return_value=state)
    resume_input = _create_resume_input("我是架构师")
    bindings.resume_input_adapter.normalize = MagicMock(return_value=resume_input)
    bindings.reducer.apply_resume = MagicMock(return_value=state)

    # Fail-soft: resume MUST succeed despite adapter/memory errors
    result = await runtime.resume(snapshot, input=resume_input)
    assert result.status is TaskStatus.COMPLETED
    assert len(bindings.driver.resumed_checkpoints) == 1


@pytest.mark.asyncio
async def test_resume_memory_capture_successful_with_real_update() -> None:
    mock_adapter = MagicMock()
    mock_adapter.complete = AsyncMock(
        return_value=MagicMock(
            text='[{"category": "identity", "content": "用户身份：架构师", "confidence": 1.0, "dedupe_key": "identity:architect"}]'
        )
    )
    mock_memory = MagicMock()
    mock_memory.update = AsyncMock()

    capabilities = RuntimePhaseCapabilities(
        {
            "adapter": mock_adapter,
            "memory": mock_memory,
        }
    )
    bindings = _DeclarativeBindingsWithoutMemoryAttribute(capabilities)
    runtime = CognitiveRuntime(bindings)  # type: ignore[arg-type]

    snapshot, state = _create_snapshot_and_state()
    bindings.state_store.load = AsyncMock(return_value=state)
    resume_input = _create_resume_input("我是架构师")
    bindings.resume_input_adapter.normalize = MagicMock(return_value=resume_input)
    bindings.reducer.apply_resume = MagicMock(return_value=state)

    result = await runtime.resume(snapshot, input=resume_input)
    assert result.status is TaskStatus.COMPLETED
    assert len(bindings.driver.resumed_checkpoints) == 1
    assert mock_memory.update.called
