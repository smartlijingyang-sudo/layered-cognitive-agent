"""ADR-0055 Run Fact Store 新增特性守卫（ADR-0063 PR-7 后从 ``JOURNAL_CATALOG_META``
迁移至 ``EventDescriptorRegistry``）。

覆盖：
- fold_run_state 纯函数推导终态（N3）
- EventDescriptorRegistry 分类声明完整性（N6 + PR-7）
- RunStore.read_from 自拉（N2）
- audience 过滤（§十三 SSE 演进）
"""

from __future__ import annotations

from lca.infrastructure.observability.events.event_catalog import EVENT_DESCRIPTOR_REGISTRY

from lca.contracts.models.observability.event import (
    EventAudience,
    EventDurability,
)
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    RunScope,
    StampedEvent,
    TeamRunFinished,
    TeamRunStarted,
)
from lca.contracts.models.observability.journal_catalog import (
    JOURNAL_EVENT_CLASSES,
)
from lca.infrastructure.observability.journal.engine.reducer import (
    RunStatus,
    fold_run_state,
)

# ── fold_run_state ───────────────────────────────────────


def _stamped(seq: int, event: object, *, parent_run_id: str | None = None) -> StampedEvent:
    return StampedEvent(
        seq=seq,
        ts=1000.0 + seq,
        scope=RunScope(trace_id="t", run_id="r", parent_run_id=parent_run_id),
        event=event,  # type: ignore[arg-type]
    )


def test_fold_empty_events_is_running() -> None:
    state = fold_run_state([])
    assert state.status == RunStatus.RUNNING
    assert state.finished_at is None


def test_fold_agent_finished_completed() -> None:
    events = [
        _stamped(1, AgentRunStarted(agent_role="助手")),
        _stamped(2, AgentRunFinished(status="completed", steps=3)),
    ]
    state = fold_run_state(events)
    assert state.status == RunStatus.COMPLETED
    assert state.error is None


def test_fold_agent_finished_error() -> None:
    events = [
        _stamped(1, AgentRunStarted(agent_role="助手")),
        _stamped(2, AgentRunFinished(status="error", error="boom")),
    ]
    state = fold_run_state(events)
    assert state.status == RunStatus.FAILED
    assert state.error == "boom"


def test_fold_team_finished_overrides_agent() -> None:
    events = [
        _stamped(1, TeamRunStarted(team_id="team-x")),
        _stamped(2, AgentRunFinished(status="completed")),
        _stamped(3, TeamRunFinished(status="error", error="team failed")),
    ]
    state = fold_run_state(events)
    assert state.status == RunStatus.FAILED
    assert state.error == "team failed"


def test_fold_member_agent_finished_ignored() -> None:
    """成员 run 的 AgentRunFinished（parent_run_id != None）不触发终态。"""
    events = [
        _stamped(1, AgentRunStarted(agent_role="member"), parent_run_id="root"),
        _stamped(2, AgentRunFinished(status="completed"), parent_run_id="root"),
    ]
    state = fold_run_state(events)
    assert state.status == RunStatus.RUNNING  # 没有根 finish 事件


def test_fold_canceled() -> None:
    events = [
        _stamped(1, AgentRunFinished(status="canceled")),
    ]
    state = fold_run_state(events)
    assert state.status == RunStatus.CANCELED


# ── EventDescriptorRegistry 完整性 ──────────────────────────


def test_all_registered_events_have_descriptor() -> None:
    """每个已登记事件必须有 EventDescriptor（N6 + ADR-0063 PR-7）。"""
    for event_name in JOURNAL_EVENT_CLASSES:
        descriptor = EVENT_DESCRIPTOR_REGISTRY.get(event_name)
        assert descriptor is not None, f"事件 {event_name} 缺少 EventDescriptor 登记"


def test_descriptor_fields_valid() -> None:
    """所有 EventDescriptor 的字段值必须在合法范围内。"""
    valid_durability = {EventDurability.REQUIRED, EventDurability.BEST_EFFORT}
    valid_audience = {
        EventAudience.END_USER,
        EventAudience.OPERATOR,
        EventAudience.AUDITOR,
        EventAudience.RESTRICTED,
    }
    for descriptor in EVENT_DESCRIPTOR_REGISTRY:
        assert descriptor.durability in valid_durability, (
            f"{descriptor.type_name}.durability={descriptor.durability!r}"
        )
        assert descriptor.audience in valid_audience, (
            f"{descriptor.type_name}.audience={descriptor.audience!r}"
        )
        assert descriptor.retention, f"{descriptor.type_name}.retention 不能为空"


def test_high_value_events_are_required() -> None:
    """容器/协作/工具完成事件必须是 required durability。"""
    required_events = {
        "TeamRunStarted",
        "TeamRunFinished",
        "AgentRunStarted",
        "AgentRunFinished",
        "DelegationIssued",
        "DelegationCompleted",
        "ToolInvoked",
        "ToolDenied",
        "LlmCallCompleted",
        "DecisionMade",
    }
    for name in required_events:
        descriptor = EVENT_DESCRIPTOR_REGISTRY.get(name)
        assert descriptor is not None, f"{name} 缺少 descriptor"
        assert descriptor.durability is EventDurability.REQUIRED, (
            f"{name}.durability 应为 required，实际 {descriptor.durability}"
        )


def test_delta_events_are_best_effort() -> None:
    """增量/心跳事件必须是 best_effort durability。"""
    best_effort_events = {
        "StepTextDelta",
        "ReasoningDelta",
        "ReasoningCompleted",
        "RunActivity",
        "SandboxOutputDelta",
    }
    for name in best_effort_events:
        descriptor = EVENT_DESCRIPTOR_REGISTRY.get(name)
        assert descriptor is not None
        assert descriptor.durability is EventDurability.BEST_EFFORT, (
            f"{name}.durability 应为 best_effort"
        )


def test_reasoning_events_are_restricted_audience() -> None:
    """Reasoning 事件 audience=restricted，不进 SSE live 帧。"""
    for name in ("ReasoningDelta", "ReasoningCompleted"):
        descriptor = EVENT_DESCRIPTOR_REGISTRY.get(name)
        assert descriptor is not None
        assert descriptor.audience is EventAudience.RESTRICTED, f"{name}.audience 应为 restricted"


# ── SSE audience 过滤 ────────────────────────────────────


def test_is_sse_visible_filters_restricted() -> None:
    from lca.infrastructure.observability.journal.sse.frames import is_sse_visible

    assert is_sse_visible("TeamRunStarted") is True
    assert is_sse_visible("AgentRunFinished") is True
    assert is_sse_visible("ReasoningDelta") is False
    assert is_sse_visible("ReasoningCompleted") is False
    with __import__("pytest").raises(KeyError):
        is_sse_visible("UnknownEvent")  # 未登记事件 → KeyError（PR-7 后收紧）
