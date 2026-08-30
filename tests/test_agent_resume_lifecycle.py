from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import Budget, StateSnapshot
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    RunResumed,
)
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.agent.cognitive_agent import CognitiveAgent
from tests.support.observability_helpers import _RunStoreBackend, make_test_bound


class _ResumeRuntime:
    def __init__(self) -> None:
        self.resumed_snapshot: StateSnapshot | None = None
        self.resume_input: object | None = None

    async def run(self, *args: Any, **kwargs: Any) -> Result:
        del args, kwargs
        raise AssertionError("resume test must not start a fresh runtime")

    async def resume(
        self,
        snapshot: StateSnapshot,
        input: object | None = None,
        max_steps: int = 0,
    ) -> Result:
        del max_steps
        self.resumed_snapshot = snapshot
        self.resume_input = input
        return Result(
            trace_id=str(snapshot.trace_id),
            status=TaskStatus.COMPLETED,
            final_state_ref=snapshot.state_ref,
            total_steps=snapshot.step + 1,
            budget_used=Budget(used_steps=snapshot.step + 1),
            output="resumed output",
        )


class _PauseRuntime:
    async def run(self, *args: Any, **kwargs: Any) -> Result:
        del args, kwargs
        snapshot = StateSnapshot(
            snapshot_id="snap-paused",
            step=2,
            state_ref="memory://state/2",
            trace_id=TraceId("trace-runtime"),
        )
        return Result(
            trace_id="trace-runtime",
            status=TaskStatus.INPUT_REQUIRED,
            final_state_ref=snapshot.state_ref,
            total_steps=2,
            budget_used=Budget(used_steps=2),
            extra={"state_snapshot": snapshot},
        )

    async def resume(self, *args: Any, **kwargs: Any) -> Result:
        del args, kwargs
        raise AssertionError("pause test must not resume")


def _role() -> RoleProfile:
    return RoleProfile(
        role="测试员",
        goal="验证恢复路径",
        backstory="用于 Agent 生命周期测试",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


@pytest.mark.asyncio
async def test_resume_uses_persisted_trace_and_records_full_agent_lifecycle() -> None:
    hub = make_test_bound()
    runtime = _ResumeRuntime()
    agent = CognitiveAgent(runtime, _role(), hub)
    snapshot = StateSnapshot(
        snapshot_id="snap-paused",
        step=2,
        state_ref="memory://state/2",
        trace_id=TraceId("trace-paused"),
        run_id=RunId("run-paused"),
    )

    result = await agent.resume(snapshot, input="approved")

    assert result.status is TaskStatus.COMPLETED
    assert runtime.resumed_snapshot is snapshot
    assert isinstance(hub.journal, _RunStoreBackend)
    events = hub.journal.store.events
    started = next(event for event in events if isinstance(event.event, AgentRunStarted))
    resumed = next(event for event in events if isinstance(event.event, RunResumed))
    finished = next(event for event in events if isinstance(event.event, AgentRunFinished))
    assert isinstance(started.event, AgentRunStarted)
    assert isinstance(resumed.event, RunResumed)
    assert isinstance(finished.event, AgentRunFinished)
    assert started.scope.trace_id == TraceId("trace-paused")
    assert started.scope.run_id != RunId("run-paused")
    assert started.scope.parent_run_id == RunId("run-paused")
    assert started.event.strategy_key == ""
    assert resumed.scope == started.scope
    assert resumed.event.step == 2
    assert finished.scope == started.scope
    assert finished.event.status == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_paused_snapshot_is_stamped_with_owning_run_scope() -> None:
    hub = make_test_bound()
    agent = CognitiveAgent(_PauseRuntime(), _role(), hub)

    result = await agent.run("需要审批的任务")

    snapshot = result.extra["state_snapshot"]
    assert isinstance(hub.journal, _RunStoreBackend)
    started = next(
        event for event in hub.journal.store.events if isinstance(event.event, AgentRunStarted)
    )
    assert isinstance(snapshot, StateSnapshot)
    assert snapshot.trace_id == started.scope.trace_id
    assert snapshot.run_id == started.scope.run_id
    assert snapshot.run_id
