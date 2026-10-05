"""RuntimeLifecycleEmitter coverage: event-type closure, cursor/sequence readers, publish projection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import Budget
from lca.contracts.protocols.runtime.runtime.lifecycle import RuntimeLifecycleEventType
from lca.runtime.loop.runtime_lifecycle_emitter import (
    RuntimeLifecycleEmitter,
    _event_type_for_result,
    _journal_sequence_from_result,
    _phase_cursor_from_result,
)


class _RecordingPublisher:
    def __init__(self, fail: bool = False) -> None:
        self.events: list = []
        self._fail = fail

    async def publish(self, event) -> None:
        if self._fail:
            raise RuntimeError("spine down")
        self.events.append(event)


class _FakeBindings:
    def __init__(self, publisher: _RecordingPublisher) -> None:
        self.lifecycle_publisher = publisher

    def plan_ref(self) -> str:
        return "plan/test-001"


def _emitter(
    publisher: _RecordingPublisher | None = None,
) -> tuple[RuntimeLifecycleEmitter, _RecordingPublisher]:
    pub = publisher or _RecordingPublisher()
    return RuntimeLifecycleEmitter(_FakeBindings(pub)), pub  # type: ignore[arg-type]


def _result(status: TaskStatus, extra: dict | None = None) -> Result:
    return Result(
        trace_id="trace-1",
        status=status,
        final_state_ref="state/ref-9",
        total_steps=3,
        budget_used=Budget(),
        extra=extra or {},
    )


def _state(**overrides) -> SimpleNamespace:
    budget = SimpleNamespace(
        max_tokens=1000,
        max_cost_usd=0.5,
        max_steps=20,
        max_wall_clock_seconds=300,
        used_tokens=120,
        used_cost_usd=0.01,
        used_steps=4,
    )
    base = {"budget": budget, "trace_id": "trace-1", "step": 7, "status": TaskStatus.WORKING}
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (TaskStatus.COMPLETED, RuntimeLifecycleEventType.COMPLETED),
        (TaskStatus.PARTIAL, RuntimeLifecycleEventType.PARTIAL),
        (TaskStatus.INPUT_REQUIRED, RuntimeLifecycleEventType.INPUT_REQUIRED),
        (TaskStatus.CANCELED, RuntimeLifecycleEventType.CANCELED),
        (TaskStatus.FAILED, RuntimeLifecycleEventType.FAILED),
        # 未映射的状态落入默认分支：闭包是 FAILED
        (TaskStatus.WORKING, RuntimeLifecycleEventType.FAILED),
        (TaskStatus.SUBMITTED, RuntimeLifecycleEventType.FAILED),
        (TaskStatus.PAUSED, RuntimeLifecycleEventType.FAILED),
    ],
)
def test_event_type_mapping_closed_set(
    status: TaskStatus, expected: RuntimeLifecycleEventType
) -> None:
    assert _event_type_for_result(_result(status)) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"node_id": "n-1", "cursor": "c-1"}, "n-1"),  # node_id 优先
        ({"cursor": "c-2"}, "c-2"),  # 只有 cursor 时回退
        ({"node_id": "", "cursor": ""}, None),  # 空串不算
        ({}, None),
        ({"other": "x"}, None),
        ("n-plain", None),  # 非 dict 无 node_id 属性
        (123, None),
    ],
)
def test_phase_cursor_extraction(raw, expected: str | None) -> None:
    assert (
        _phase_cursor_from_result(_result(TaskStatus.COMPLETED, {"phase_cursor": raw})) == expected
    )


def test_phase_cursor_from_object_with_node_id() -> None:
    holder = SimpleNamespace(node_id="n-obj")
    assert (
        _phase_cursor_from_result(_result(TaskStatus.COMPLETED, {"phase_cursor": holder}))
        == "n-obj"
    )
    assert (
        _phase_cursor_from_result(
            _result(TaskStatus.COMPLETED, {"phase_cursor": SimpleNamespace(node_id=7)})
        )
        is None
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (5, 5),
        (0, 0),
        (True, None),  # bool 不是合法序号
        (-1, None),
        ("5", None),
        (None, None),
    ],
)
def test_journal_sequence_validation(raw, expected: int | None) -> None:
    assert (
        _journal_sequence_from_result(_result(TaskStatus.COMPLETED, {"journal_seq_end": raw}))
        == expected
    )


def test_journal_sequence_missing_is_none() -> None:
    assert _journal_sequence_from_result(_result(TaskStatus.COMPLETED)) is None


async def test_publish_projects_event() -> None:
    emitter, pub = _emitter()
    await emitter.publish(
        RuntimeLifecycleEventType.PHASE_COMPLETED,
        _state(),
        status=TaskStatus.COMPLETED,
        state_ref="state/ref-1",
        phase_cursor="n-1",
        journal_sequence=42,
        trace_id="trace-explicit",
    )
    assert len(pub.events) == 1
    event = pub.events[0]
    assert event.type is RuntimeLifecycleEventType.PHASE_COMPLETED
    assert event.trace_id == "trace-explicit"
    assert event.plan_ref == "plan/test-001"
    assert event.status is TaskStatus.COMPLETED
    assert event.step == 7
    assert event.state_ref == "state/ref-1"
    assert event.phase_cursor == "n-1"
    assert event.journal_sequence == 42
    # 预算快照逐字段投影
    assert event.budget.max_tokens == 1000
    assert event.budget.max_cost_usd == 0.5
    assert event.budget.max_steps == 20
    assert event.budget.max_wall_clock_seconds == 300
    assert event.budget.used_tokens == 120
    assert event.budget.used_cost_usd == 0.01
    assert event.budget.used_steps == 4


async def test_publish_status_falls_back_to_working() -> None:
    emitter, pub = _emitter()
    # 显式 status=None 且 state 无 status → WORKING
    state = SimpleNamespace(budget=None, trace_id="t", step=0)
    await emitter.publish(RuntimeLifecycleEventType.STARTED, state)
    assert pub.events[0].status is TaskStatus.WORKING
    assert pub.events[0].trace_id == "t"

    # state.status 非法值 → WORKING
    await emitter.publish(RuntimeLifecycleEventType.STARTED, _state(status="garbage"))
    assert pub.events[1].status is TaskStatus.WORKING


async def test_publish_trace_id_falls_back_to_state() -> None:
    emitter, pub = _emitter()
    await emitter.publish(RuntimeLifecycleEventType.STARTED, _state(), status=TaskStatus.WORKING)
    assert pub.events[0].trace_id == "trace-1"


async def test_publish_terminal_maps_result() -> None:
    emitter, pub = _emitter()
    result = _result(
        TaskStatus.COMPLETED,
        {"phase_cursor": {"node_id": "n-9"}, "journal_seq_end": 17},
    )
    await emitter.publish_terminal(_state(), result)
    assert len(pub.events) == 1
    event = pub.events[0]
    assert event.type is RuntimeLifecycleEventType.COMPLETED
    assert event.status is TaskStatus.COMPLETED
    assert event.state_ref == "state/ref-9"
    assert event.phase_cursor == "n-9"
    assert event.journal_sequence == 17
    assert event.trace_id == "trace-1"


async def test_publish_propagates_publisher_failure() -> None:
    emitter, _ = _emitter(_RecordingPublisher(fail=True))
    with pytest.raises(RuntimeError, match="spine down"):
        await emitter.publish(RuntimeLifecycleEventType.STARTED, _state())
