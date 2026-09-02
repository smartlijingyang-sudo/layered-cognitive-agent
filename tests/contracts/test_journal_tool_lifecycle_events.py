"""ADR-0159 / ADR-0162 闭集事件登记与契约测试。

新增三类 JournalEvent 的存在性 + 默认值 + catalog 注册:

- ``ToolLifecycleEnded`` —— 事实,用户能感知(失败/取消/被替换)
- ``ToolAbandonedBeforeInvoke`` —— best_effort,占位回收但用户没感知
- ``ToolRetryProgress`` —— best_effort,UI 实时重试提示

闭集约束:JournalCatalog 必须含这三类;且 ``ToolLifecycleEndKind`` 枚举不再含
``NOT_INVOKED_AFTER_STREAM``(已迁出至 ToolAbandonedBeforeInvoke,ADR-0162 决策 一)。
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import (
    JournalEvent,
    ToolAbandonedBeforeInvoke,
    ToolLifecycleEnded,
    ToolRetryProgress,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES


def test_tool_lifecycle_ended_is_registered_in_catalog() -> None:
    assert "ToolLifecycleEnded" in JOURNAL_EVENT_CLASSES
    assert JOURNAL_EVENT_CLASSES["ToolLifecycleEnded"] is ToolLifecycleEnded


def test_tool_abandoned_before_invoke_is_registered_in_catalog() -> None:
    assert "ToolAbandonedBeforeInvoke" in JOURNAL_EVENT_CLASSES
    assert JOURNAL_EVENT_CLASSES["ToolAbandonedBeforeInvoke"] is ToolAbandonedBeforeInvoke


def test_tool_retry_progress_is_registered_in_catalog() -> None:
    assert "ToolRetryProgress" in JOURNAL_EVENT_CLASSES
    assert JOURNAL_EVENT_CLASSES["ToolRetryProgress"] is ToolRetryProgress


def test_tool_lifecycle_ended_defaults() -> None:
    """默认构造应满足 'tool_call_id + end_kind + phase_id' 三必填。"""

    event = ToolLifecycleEnded(tool_call_id="t-1", end_kind="failed", phase_id="n-1")
    assert event.tool_call_id == "t-1"
    assert event.end_kind == "failed"
    assert event.phase_id == "n-1"
    assert event.error == ""
    assert isinstance(event, JournalEvent)


def test_tool_abandoned_before_invoke_defaults() -> None:
    event = ToolAbandonedBeforeInvoke(
        tool_call_id="t-2",
        phase_id="n-2",
        reason="phase_retried",
    )
    assert event.tool_call_id == "t-2"
    assert event.phase_id == "n-2"
    assert event.reason == "phase_retried"
    assert isinstance(event, JournalEvent)


def test_tool_retry_progress_defaults() -> None:
    event = ToolRetryProgress(
        tool_call_id="t-3",
        phase_id="n-3",
        attempt=2,
        of=3,
    )
    assert event.tool_call_id == "t-3"
    assert event.phase_id == "n-3"
    assert event.attempt == 2
    assert event.of == 3
    assert isinstance(event, JournalEvent)


def test_tool_lifecycle_end_kind_excludes_not_invoked_after_stream() -> None:
    """ADR-0162 决策 一:TLE 枚举收窄为「用户能感知」三类,NOT_INVOKED_AFTER_STREAM 迁出。"""

    from lca.contracts.models.observability.journal import ToolLifecycleEndKind

    members = {m.name for m in ToolLifecycleEndKind}
    assert "NOT_INVOKED_AFTER_STREAM" not in members
    assert {"CANCELLED", "FAILED", "SUPERSEDED"}.issubset(members)


def test_events_are_immutable() -> None:
    """ADR-0063:C1 闭集事件不可变,避免消费方就地改写破坏事实流。"""

    event = ToolLifecycleEnded(tool_call_id="t-1", end_kind="failed", phase_id="n-1")
    with_test_immutable_failed(event)

    event = ToolAbandonedBeforeInvoke(
        tool_call_id="t-2",
        phase_id="n-2",
        reason="phase_retried",
    )
    with_test_immutable_failed(event)

    event = ToolRetryProgress(
        tool_call_id="t-3",
        phase_id="n-3",
        attempt=2,
        of=3,
    )
    with_test_immutable_failed(event)


def with_test_immutable_failed(_event: JournalEvent) -> None:
    """frozen=True 时 setattr 抛 FrozenInstanceError;以 dataclass 抛 FrozenInstanceError。"""

    import dataclasses

    try:
        # type: ignore[attr-defined]
        _event.tool_call_id = "modified"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("expected frozen event to reject mutation")
