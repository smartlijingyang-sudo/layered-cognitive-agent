from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest

from lca.cognition.body.actions.action_handlers import UseToolOperation
from lca.cognition.body.tools.tool_batch_execution import (
    ParallelToolBatchExecutionPolicy,
    SafeToolBatchExecutionPolicy,
    SegmentedSafeToolBatchExecutionPolicy,
    SequentialToolBatchExecutionPolicy,
)
from lca.cognition.body.tools.tool_batch_executor import ToolBatchExecutor
from lca.contracts.atoms.enums.enums import ActionType, MemoryRecordKind
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    OBS_RESULT_KIND,
    OBS_TOOL_RESULTS,
)
from lca.contracts.harness.act.effect_receipt import EffectReceipt
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall
from lca.contracts.models.core.execution.result import ToolExecutionError
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.act.tool.batch_execution import (
    ToolBatchEntry,
    ToolBatchExecutionMode,
    ToolBatchExecutionSegment,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.plugins.act.tool.batch_execution_policy_provider import build_tool_batch_execution_policy


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
async def test_batch_executor_falls_back_to_canonicalised_name() -> None:
    """LLM 偶尔 emit snake_case name (e.g. ``export_file``);registry 是 camelCase
    (``exportFile``)。ToolBatchExecutor 必须做 snake↔camel 容错 lookup,以避免
    误报 ``未注册工具: export_file``。

    这是 LLM name hallucination 的实际修复 —— 不修改 wire name(仍然 emit
    snake_case 进 journal),只在 dispatch 前 normalize 解析。
    """

    camel_tool = _Tool("exportFile", is_idempotent=True)
    safe_executor = _RecordingSafeExecutor()
    batch_executor = ToolBatchExecutor(
        _ToolRegistry(camel_tool),
        safe_executor,
        policy=SafeToolBatchExecutionPolicy(),
    )

    # LLM emits snake_case; resolver must find the camelCase tool.
    decision = _decision("export_file")
    observation = await batch_executor.execute(decision.tool_calls)

    assert observation.success
    assert safe_executor.invocations == ["exportFile"]


@pytest.mark.asyncio
async def test_batch_executor_marks_single_result_as_tool_result() -> None:
    """单工具路径与批次路径共享工具结果类别这一测试表面。"""

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


class _ScriptedSafeExecutor:
    """SafeExecutor stub returning a scripted Observation per tool name."""

    def __init__(self, outcomes: dict[str, Observation]) -> None:
        self._outcomes = outcomes

    async def execute(
        self,
        tool: _Tool,
        args: dict[str, Any],
        retry_policy: object,
        cache_config: object,
        invocation_id: str = "",
    ) -> Observation:
        del args, retry_policy, cache_config, invocation_id
        return self._outcomes[tool.name]


def _ok(name: str) -> Observation:
    return Observation(
        observation_id=f"obs-{name}", success=True, payload=name, tool_call_id=f"call-{name}"
    )


def _failed(name: str, *, failure_kind: str | None, error: str = "boom") -> Observation:
    return Observation(
        observation_id=f"obs-{name}",
        success=False,
        payload=None,
        tool_call_id=f"call-{name}",
        error=error,
        extra={} if failure_kind is None else {FAILURE_KIND: failure_kind},
    )


async def _run_batch(outcomes: dict[str, Observation], *names: str) -> Observation:
    tools = tuple(_Tool(name, is_idempotent=True) for name in names)
    executor = ToolBatchExecutor(
        _ToolRegistry(*tools),
        _ScriptedSafeExecutor(outcomes),
        policy=ParallelToolBatchExecutionPolicy(),
    )
    return await executor.execute(_decision(*names).tool_calls)


@pytest.mark.asyncio
async def test_forked_batch_keeps_the_failing_tools_classification() -> None:
    """run_136671e2ff8a:一个 turn fork 出 2 个调用,其中一个确定性失败。

    聚合体丢掉分类 → receipt.failure_kind=None →
    ``act.observe.terminate_decide`` 把它读成「host 没能把 effect 派出去」→
    run 在第 1 步收口(``terminal.commit`` 拿到的却还是
    ``StopPayload(reason='continue')``)。模型从没看到那条
    ``cd: /files: No such file or directory``,也就没有换路径的机会。
    """

    observation = await _run_batch(
        {
            "runCommand": _failed(
                "runCommand",
                failure_kind=FAILURE_KIND_EXECUTION,
                error="/bin/sh: line 0: cd: /files: No such file or directory",
            ),
            "activate_skill": _ok("activate_skill"),
        },
        "runCommand",
        "activate_skill",
    )

    assert not observation.success
    assert observation.extra[FAILURE_KIND] == FAILURE_KIND_EXECUTION
    # 聚合分类不替代每调用明细:surface/tool_result 与 critic 仍读这个袋子。
    assert [entry["tool_name"] for entry in observation.extra[OBS_TOOL_RESULTS]] == [
        "runCommand",
        "activate_skill",
    ]


@pytest.mark.parametrize("order", [("flaky", "broken"), ("broken", "flaky")])
@pytest.mark.asyncio
async def test_forked_batch_classification_is_order_independent(order: tuple[str, str]) -> None:
    """同批出现多种分类时取优先级更高者,与模型 emit 顺序和并发调度无关(C8)。"""

    observation = await _run_batch(
        {
            "flaky": _failed("flaky", failure_kind=FAILURE_KIND_TRANSIENT),
            "broken": _failed("broken", failure_kind=FAILURE_KIND_EXECUTION),
        },
        *order,
    )

    assert observation.extra[FAILURE_KIND] == FAILURE_KIND_EXECUTION


@pytest.mark.asyncio
async def test_successful_batch_carries_no_failure_kind() -> None:
    observation = await _run_batch({"read": _ok("read"), "search": _ok("search")}, "read", "search")

    assert observation.success
    assert FAILURE_KIND not in observation.extra


@pytest.mark.asyncio
async def test_batch_of_unclassified_failures_stays_unclassified() -> None:
    """没有分量带分类时聚合体也不带 —— 不能把「无工具报告」伪造成别的读数。"""

    observation = await _run_batch(
        {"read": _failed("read", failure_kind=None), "search": _ok("search")},
        "read",
        "search",
    )

    assert not observation.success
    assert FAILURE_KIND not in observation.extra


@pytest.mark.asyncio
async def test_forked_batch_failure_does_not_terminate_the_run() -> None:
    """跨边界不变量:Body 聚合 → ``_derive_outcome`` → receipt → terminate_decide。

    两侧各自的单测都曾通过,坏在中间那一跳,所以这条链必须整体钉住。
    """
    from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor
    from lca.nodes.concept.effect.execute import _derive_outcome

    aggregate = await _run_batch(
        {
            "runCommand": _failed("runCommand", failure_kind=FAILURE_KIND_EXECUTION),
            "activate_skill": _ok("activate_skill"),
        },
        "runCommand",
        "activate_skill",
    )
    outcome, error_code, failure_kind = _derive_outcome(aggregate)

    receipt = EffectReceipt(
        invocation_id="inv_batch",
        outcome=outcome,
        idempotency_key="idem_batch",
        provider="body.act",
        error_code=error_code,
        failure_kind=failure_kind,
    )
    assert receipt.failure_kind == FAILURE_KIND_EXECUTION

    output = await ActObserveTerminateDecideExecutor().node_execute(
        NodeContext(runtime={}, budget={}, metadata={"plan_ref": "test"}),
        NodeInput({"receipt": receipt}),
    )

    assert output.port_values["should_terminate"] is False
