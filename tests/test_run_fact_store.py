"""ADR-0055 Run Fact Store 新增特性守卫。

覆盖：
- fold_run_state 纯函数推导终态（N3）
- JOURNAL_CATALOG_META 分类声明完整性（N6）
- RunStore.read_from 自拉（N2）
- audience 过滤（§十三 SSE 演进）
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    RunScope,
    StampedEvent,
    TeamRunFinished,
    TeamRunStarted,
)
from lca.contracts.models.observability.journal_catalog import (
    JOURNAL_CATALOG_META,
    JOURNAL_EVENT_CLASSES,
    JournalSchemaMeta,
)
from lca.layer0_infra.observability.journal.reducer import (
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


# ── JOURNAL_CATALOG_META 完整性 ──────────────────────────


def test_all_registered_events_have_schema_meta() -> None:
    """每个已登记事件必须有 JournalSchemaMeta 声明（N6）。"""
    for event_name in JOURNAL_EVENT_CLASSES:
        assert event_name in JOURNAL_CATALOG_META, f"事件 {event_name} 缺少 JournalSchemaMeta 声明"


def test_schema_meta_fields_valid() -> None:
    """所有 JournalSchemaMeta 的字段值必须在合法范围内。"""
    valid_durability = {"required", "best_effort"}
    valid_audience = {"end_user", "operator", "auditor", "restricted"}
    valid_sensitivity = {"public", "internal", "confidential"}
    for name, meta in JOURNAL_CATALOG_META.items():
        assert isinstance(meta, JournalSchemaMeta), f"{name} 的 meta 不是 JournalSchemaMeta"
        assert meta.durability in valid_durability, f"{name}.durability={meta.durability!r}"
        assert meta.audience in valid_audience, f"{name}.audience={meta.audience!r}"
        assert meta.sensitivity in valid_sensitivity, f"{name}.sensitivity={meta.sensitivity!r}"
        assert meta.retention_class, f"{name}.retention_class 不能为空"


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
        meta = JOURNAL_CATALOG_META.get(name)
        assert meta is not None, f"{name} 缺少 catalog meta"
        assert meta.durability == "required", (
            f"{name}.durability 应为 required，实际 {meta.durability}"
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
        meta = JOURNAL_CATALOG_META.get(name)
        assert meta is not None
        assert meta.durability == "best_effort", f"{name}.durability 应为 best_effort"


def test_reasoning_events_are_restricted_audience() -> None:
    """Reasoning 事件 audience=restricted，不进 SSE live 帧。"""
    for name in ("ReasoningDelta", "ReasoningCompleted"):
        meta = JOURNAL_CATALOG_META[name]
        assert meta.audience == "restricted", f"{name}.audience 应为 restricted"


# ── SSE audience 过滤 ────────────────────────────────────


def test_is_sse_visible_filters_restricted() -> None:
    from lca.layer0_infra.observability.journal.sse_frames import is_sse_visible

    assert is_sse_visible("TeamRunStarted") is True
    assert is_sse_visible("AgentRunFinished") is True
    assert is_sse_visible("ReasoningDelta") is False
    assert is_sse_visible("ReasoningCompleted") is False
    assert is_sse_visible("UnknownEvent") is True  # 未分类默认可见
