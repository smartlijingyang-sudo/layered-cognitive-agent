"""ADR-0157 commit 1:projector 加 ToolCallStreaming 合并键。

约束(ADR-0157 决策 一 + commit 45a5f462 现状):
- ToolCallStreaming 当前字段:tool_name/tool_call_id/arguments_preview/arguments_ref
- 字段 ``arguments_preview`` 是累积字典(commit 45a5f462 已落地)
- ADR-0157 决策 一要求 projector 给 ToolCallStreaming 加
  ``(ToolCallStreaming, tool_call_id)`` 合并键,使同 tool_call_id 的多 chunk
  合并为一次落盘
- 不同 ``tool_call_id`` 的 ToolCallStreaming 不互相合并
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
    ToolCallStreaming,
)
from lca.infrastructure.observability.journal.jsonl.projector import _delta_key


def _stamped(event: object) -> StampedEvent:
    return StampedEvent(seq=1, ts=0.0, scope=RunScope(), event=event)


def test_tool_call_streaming_has_delta_merge_key_by_tool_call_id() -> None:
    """ADR-0157 决策 一:同 tool_call_id 的多 chunk 合并键。"""

    event = ToolCallStreaming(
        tool_call_id="t-1",
        tool_name="chart_generator",
        arguments_preview={"code": "x = 1"},
    )
    key = _delta_key(_stamped(event))
    assert key is not None
    assert key == ("ToolCallStreaming", "t-1")


def test_different_tool_call_ids_produce_different_merge_keys() -> None:
    e1 = ToolCallStreaming(
        tool_call_id="t-1",
        tool_name="chart_generator",
        arguments_preview={},
    )
    e2 = ToolCallStreaming(
        tool_call_id="t-2",
        tool_name="chart_generator",
        arguments_preview={},
    )
    k1 = _delta_key(_stamped(e1))
    k2 = _delta_key(_stamped(e2))
    assert k1 is not None and k2 is not None
    assert k1 != k2


def test_tool_call_streaming_without_tool_call_id_has_no_merge_key() -> None:
    """空 tool_call_id 不应合并(占位未实例化的 ToolCallStreaming 不应冲掉已有)。"""

    event = ToolCallStreaming(
        tool_call_id="",
        tool_name="chart_generator",
        arguments_preview={},
    )
    key = _delta_key(_stamped(event))
    # ADR-0157 决策 一:无 tool_call_id 不合并,落到 N 个独立事件
    # 注:返回 None 让其走默认 not-coalesced 路径;或者返回唯一键
    # 当前决策是返回 None,避免空 ID 串到一个固定桶
    assert key is None