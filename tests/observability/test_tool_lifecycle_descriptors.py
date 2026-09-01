"""ADR-0159 / ADR-0162 EventDescriptor + _delta_key 合并测试。

闭集约束验证:

- ``ToolLifecycleEnded`` 必须有 EventDescriptor,durability=required
- ``ToolAbandonedBeforeInvoke`` 必须有 EventDescriptor,durability=best_effort
- ``ToolRetryProgress`` 必须有 EventDescriptor,durability=best_effort 且
  ``_delta_key`` 返回合并键(走 ADR-0157 同范式)
"""

from __future__ import annotations

from lca.contracts.models.observability.event import EventDurability
from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
    ToolAbandonedBeforeInvoke,
    ToolLifecycleEnded,
    ToolRetryProgress,
)
from lca.infrastructure.observability.events.event_catalog import descriptor_for
from lca.infrastructure.observability.events.event_descriptors_data import (
    build_default_registry,
)
from lca.infrastructure.observability.journal.jsonl.projector import _delta_key


def _stamped(event: object) -> StampedEvent:
    return StampedEvent(seq=1, ts=0.0, scope=RunScope(), event=event)


def test_tool_lifecycle_ended_has_required_descriptor() -> None:
    build_default_registry()
    descriptor = descriptor_for("ToolLifecycleEnded")
    assert descriptor is not None
    assert descriptor.durability == EventDurability.REQUIRED


def test_tool_abandoned_before_invoke_has_best_effort_descriptor() -> None:
    build_default_registry()
    descriptor = descriptor_for("ToolAbandonedBeforeInvoke")
    assert descriptor is not None
    assert descriptor.durability == EventDurability.BEST_EFFORT


def test_tool_retry_progress_has_best_effort_descriptor() -> None:
    build_default_registry()
    descriptor = descriptor_for("ToolRetryProgress")
    assert descriptor is not None
    assert descriptor.durability == EventDurability.BEST_EFFORT


def test_tool_retry_progress_has_delta_merge_key() -> None:
    """ADR-0157 范式:同 (类型, phase_id) 多次 record 应被合并为一次落盘。"""

    event = ToolRetryProgress(
        tool_call_id="t-1",
        phase_id="n-1",
        attempt=2,
        of=3,
    )
    key = _delta_key(_stamped(event))
    assert key is not None
    assert key == ("ToolRetryProgress", "n-1")


def test_tool_abandoned_before_invoke_has_delta_merge_key() -> None:
    """best_effort 资源事件应走 _delta_key 合并(避免重 retry 期 journal 膨胀)。"""

    event = ToolAbandonedBeforeInvoke(
        tool_call_id="t-1",
        phase_id="n-1",
        reason="phase_retried",
    )
    key = _delta_key(_stamped(event))
    assert key is not None
    assert key == ("ToolAbandonedBeforeInvoke", "n-1")


def test_tool_lifecycle_ended_is_not_delta_coalesced() -> None:
    """事实事件(durability=required)不应走合并;每次失败/取消都需落盘。"""

    event = ToolLifecycleEnded(
        tool_call_id="t-1",
        end_kind="failed",
        phase_id="n-1",
    )
    key = _delta_key(_stamped(event))
    assert key is None