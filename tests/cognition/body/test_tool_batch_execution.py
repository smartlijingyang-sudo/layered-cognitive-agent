from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest

from lca.contracts.atoms.enums import ActionType, MemoryRecordKind
from lca.contracts.atoms.semantic_keys import OBS_RESULT_KIND
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision, Observation, ToolCall
from lca.contracts.models.core.result import ToolExecutionError
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.act.tool_batch_execution import (
    ToolBatchEntry,
    ToolBatchExecutionMode,
    ToolBatchExecutionSegment,
)
from lca.cognition.body.action_handlers import UseToolOperation
from lca.cognition.body.tool_batch_execution import (
    ParallelToolBatchExecutionPolicy,
    SafeToolBatchExecutionPolicy,
    SegmentedSafeToolBatchExecutionPolicy,
    SequentialToolBatchExecutionPolicy,
)
from lca.plugins.providers.act.tool_batch_execution_policy import build_tool_batch_execution_policy


class _Tool:
    description = "test tool"
    parameters: ClassVar[dict[str, object]] = {}
    default_timeout_s = 30

    def __init__(self, name: str, *, is_idempotent: bool) -> None:
        self.name = name
        self.is_idempotent = is_idempotent

    async def execute(self, args: dict[str, Any]) -> Observation:
        del args
        raise AssertionError("UseToolOperation must delegate through SafeExecutor")

    def validate(self, args: dict[str, Any]) -> str | None:
        del args
        return None


class _ToolRegistry:
    def __init__(self, *tools: _Tool) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def get(self, name: str) -> _Tool | None:
        return self._tools.get(name)


class _RecordingSafeExecutor:
    def __init__(self, *, delay_seconds: float = 0.01) -> None:
        self._delay_seconds = delay_seconds
        self.active = 0
        self.max_active = 0
        self.invocations: list[str] = []

    async def execute(
        self,
        tool: _Tool,
        args: dict[str, Any],
        retry_policy: object,
        cache_config: object,
        invocation_id: str = "",
    ) -> Observation:
        del args, retry_policy, cache_config, invocation_id
        self.invocations.append(tool.name)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self._delay_seconds)
        finally:
            self.active -= 1
        return Observation(
            observation_id=f"obs-{tool.name}",
            success=True,
            payload=tool.name,
            tool_call_id=f"call-{tool.name}",
        )


def _decision(*names: str) -> Decision:
    return Decision(
        decision_id="decision-1",
        action_type=ActionType.USE_TOOL.value,
        rationale="",
        confidence=1.0,
        tool_calls=[
            ToolCall(call_id=f"call-{name}", tool_name=name, arguments={}) for name in names
        ],
    )


def _state() -> AgentState:
    return AgentState(trace_id="trace-1", task="test tool batch", budget=create_budget())


def test_safe_policy_parallelizes_only_fully_idempotent_batches() -> None:
    policy = SafeToolBatchExecutionPolicy()

    assert (
        policy.select_mode(
            (
                ToolBatchEntry("call-read", "read", True),
                ToolBatchEntry("call-search", "search", True),
            )
        )
        is ToolBatchExecutionMode.PARALLEL
    )
    assert (
        policy.select_mode(
            (
                ToolBatchEntry("call-read", "read", True),
                ToolBatchEntry("call-write", "write", False),
            )
        )
        is ToolBatchExecutionMode.SEQUENTIAL
    )


def test_segmented_safe_policy_splits_mixed_batches_at_side_effect_barriers() -> None:
    policy = SegmentedSafeToolBatchExecutionPolicy()

    assert policy.select_segments(
        (
            ToolBatchEntry("call-read-1", "read-1", True),
            ToolBatchEntry("call-read-2", "read-2", True),
            ToolBatchEntry("call-write", "write", False),
            ToolBatchEntry("call-search", "search", True),
            ToolBatchEntry("call-stat", "stat", True),
        )
    ) == (
        ToolBatchExecutionSegment(0, 2, ToolBatchExecutionMode.PARALLEL),
        ToolBatchExecutionSegment(2, 3, ToolBatchExecutionMode.SEQUENTIAL),
        ToolBatchExecutionSegment(3, 5, ToolBatchExecutionMode.PARALLEL),
    )


@pytest.mark.asyncio
async def test_segmented_safe_policy_parallelizes_only_runs_between_side_effect_barriers() -> None:
    read_first = _Tool("read-first", is_idempotent=True)
    read_second = _Tool("read-second", is_idempotent=True)
    write = _Tool("write", is_idempotent=False)
    search = _Tool("search", is_idempotent=True)
    stat = _Tool("stat", is_idempotent=True)
    executor = _RecordingSafeExecutor()
    operation = UseToolOperation(
        _ToolRegistry(read_first, read_second, write, search, stat),
        executor,
        batch_execution_policy=SegmentedSafeToolBatchExecutionPolicy(),
    )

    observation = await operation.execute(
        _decision("read-first", "read-second", "write", "search", "stat"), _state()
    )

    assert observation.success
    assert executor.invocations == ["read-first", "read-second", "write", "search", "stat"]
    assert executor.max_active == 2
    assert [entry["tool_name"] for entry in observation.extra["tool_results"]] == [
        "read-first",
        "read-second",
        "write",
        "search",
        "stat",
    ]


class _InvalidSegmentPolicy:
    def select_mode(self, entries: tuple[ToolBatchEntry, ...]) -> ToolBatchExecutionMode:
        del entries
        return ToolBatchExecutionMode.SEQUENTIAL

    def select_segments(
        self, entries: tuple[ToolBatchEntry, ...]
    ) -> tuple[ToolBatchExecutionSegment, ...]:
        del entries
        return (ToolBatchExecutionSegment(1, 2, ToolBatchExecutionMode.SEQUENTIAL),)


@pytest.mark.asyncio
async def test_segmented_policy_rejects_non_contiguous_plan_before_dispatch() -> None:
    first = _Tool("first", is_idempotent=True)
    second = _Tool("second", is_idempotent=True)
    executor = _RecordingSafeExecutor()
    operation = UseToolOperation(
        _ToolRegistry(first, second),
        executor,
        batch_execution_policy=_InvalidSegmentPolicy(),
    )

    with pytest.raises(ToolExecutionError, match="contiguous"):
        await operation.execute(_decision("first", "second"), _state())

    assert executor.invocations == []


@pytest.mark.asyncio
async def test_safe_policy_preserves_order_for_non_idempotent_batch() -> None:
    read = _Tool("read", is_idempotent=True)
    write = _Tool("write", is_idempotent=False)
    executor = _RecordingSafeExecutor()
    operation = UseToolOperation(
        _ToolRegistry(read, write),
        executor,
        batch_execution_policy=SafeToolBatchExecutionPolicy(),
    )

    observation = await operation.execute(_decision("read", "write"), _state())

    assert observation.success
    assert executor.invocations == ["read", "write"]
    assert executor.max_active == 1


@pytest.mark.asyncio
async def test_safe_policy_keeps_idempotent_batch_concurrent() -> None:
    read = _Tool("read", is_idempotent=True)
    search = _Tool("search", is_idempotent=True)
    executor = _RecordingSafeExecutor()
    operation = UseToolOperation(
        _ToolRegistry(read, search),
        executor,
        batch_execution_policy=SafeToolBatchExecutionPolicy(),
    )

    observation = await operation.execute(_decision("read", "search"), _state())

    assert observation.success
    assert executor.max_active == 2


@pytest.mark.asyncio
async def test_explicit_policy_can_force_parallel_or_sequential_execution() -> None:
    first = _Tool("first", is_idempotent=False)
    second = _Tool("second", is_idempotent=False)

    parallel_executor = _RecordingSafeExecutor()
    parallel = UseToolOperation(
        _ToolRegistry(first, second),
        parallel_executor,
        batch_execution_policy=ParallelToolBatchExecutionPolicy(),
    )
    await parallel.execute(_decision("first", "second"), _state())

    sequential_executor = _RecordingSafeExecutor()
    sequential = UseToolOperation(
        _ToolRegistry(first, second),
        sequential_executor,
        batch_execution_policy=SequentialToolBatchExecutionPolicy(),
    )
    await sequential.execute(_decision("first", "second"), _state())

    assert parallel_executor.max_active == 2
    assert sequential_executor.max_active == 1


@pytest.mark.parametrize(
    ("mode", "expected_type"),
    [
        ("safe", SafeToolBatchExecutionPolicy),
        ("segmented_safe", SegmentedSafeToolBatchExecutionPolicy),
        ("parallel", ParallelToolBatchExecutionPolicy),
        ("sequential", SequentialToolBatchExecutionPolicy),
    ],
)
def test_provider_builds_the_configured_policy(mode: str, expected_type: type[object]) -> None:
    assert isinstance(build_tool_batch_execution_policy(mode), expected_type)


def test_provider_rejects_unknown_policy_mode() -> None:
    with pytest.raises(ValueError, match="unsupported tool batch execution mode"):
        build_tool_batch_execution_policy("not-a-policy")


@pytest.mark.asyncio
async def test_batch_executor_resolves_every_tool_before_dispatch() -> None:
    """缺少任一工具时，批次接缝不得启动部分世界副作用。"""

    from lca.cognition.body.tool_batch_executor import ToolBatchExecutor

    available = _Tool("available", is_idempotent=True)
    executor = _RecordingSafeExecutor()
    batch_executor = ToolBatchExecutor(
        _ToolRegistry(available),
        executor,
        policy=SafeToolBatchExecutionPolicy(),
    )

    with pytest.raises(ToolExecutionError, match="未注册工具: missing"):
        await batch_executor.execute(
            _decision("available", "missing").tool_calls,
        )

    assert executor.invocations == []


@pytest.mark.asyncio
async def test_batch_executor_marks_single_result_as_tool_result() -> None:
    """单工具路径与批次路径共享工具结果类别这一测试表面。"""

    from lca.cognition.body.tool_batch_executor import ToolBatchExecutor

    read = _Tool("read", is_idempotent=True)
    executor = _RecordingSafeExecutor()
    batch_executor = ToolBatchExecutor(
        _ToolRegistry(read),
        executor,
        policy=SafeToolBatchExecutionPolicy(),
    )

    observation = await batch_executor.execute(_decision("read").tool_calls)

    assert observation.success
    assert observation.extra[OBS_RESULT_KIND] is MemoryRecordKind.TOOL_RESULT
    assert executor.invocations == ["read"]
