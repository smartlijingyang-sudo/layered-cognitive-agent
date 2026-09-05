"""SpineEventPayload 校验（ADR-0181 D2）。"""
from __future__ import annotations

import pytest

from lca_kernel.events.payloads import (
    SPINE_EXECUTION_POINTS,
    Category,
    SpineEventPayload,
)


def test_execution_point_whitelist_contains_pilot_ep() -> None:
    """SPINE_EXECUTION_POINTS 闭集必须含试点 EP。"""
    assert "brain.perceive.start" in SPINE_EXECUTION_POINTS


def test_pilot_ep_passes_validation() -> None:
    """试点 EP 通过 __post_init__ 校验。"""
    p = SpineEventPayload(
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )
    assert p.execution_point == "brain.perceive.start"
    assert p.channel == "fact"
    assert p.payload == {"state_id": "s1"}


def test_unknown_ep_raises() -> None:
    """未知 EP → ValueError（fail-fast，I12 同构）。

    注意：mode="before" validator 在 category 派生时已先 raise "未登记 category 映射"；
    在白名单内的 EP 才进入 mode="after" 的 "UnknownSpineExecutionPoint" 校验。
    未知 EP 必不在白名单 → 必不在 _SPINE_EP_TO_CATEGORY → 模式"before" 先 raise。
    """
    with pytest.raises(ValueError, match="未登记 category 映射"):
        SpineEventPayload(execution_point="not.in.whitelist")


def test_unknown_channel_raises() -> None:
    """未知 channel → ValueError。"""
    with pytest.raises(ValueError, match="UnknownSpineChannel"):
        SpineEventPayload(execution_point="brain.perceive.start", channel="bogus")


def test_category_mapping_for_pilot_ep() -> None:
    """试点 EP → category 映射正确。"""
    p = SpineEventPayload(execution_point="brain.perceive.start")
    assert p.category == Category("spine.cognition.brain.perceive.start")


def test_all_spine_execution_points_have_category_mapping() -> None:
    """SPINE_EXECUTION_POINTS 闭集内每个 EP 都必须登记 category 映射。"""
    from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

    missing = sorted(ep for ep in SPINE_EXECUTION_POINTS if ep not in _SPINE_EP_TO_CATEGORY)
    assert missing == [], f"missing _SPINE_EP_TO_CATEGORY entries: {missing}"


def test_loop_cursor_record_ep_passes_validation() -> None:
    """loop cursor record_* EP 经 EventBus 路径时不应再 fail-fast。"""
    p = SpineEventPayload(
        execution_point="step.tool_call.record",
        channel="fact",
        payload={"tool_name": "search_skill"},
    )
    assert p.category == Category("spine.step.tool_call.record")


def test_pilot_ep_in_whitelist() -> None:
    """SPINE_EXECUTION_POINTS 闭集含 76 EP（包括试点 + 余下 75）。"""
    assert len(SPINE_EXECUTION_POINTS) >= 1
    assert "brain.perceive.start" in SPINE_EXECUTION_POINTS


def test_extra_fields_forbidden() -> None:
    """pydantic extra=forbid：未知字段 raise。"""
    with pytest.raises(ValueError):
        SpineEventPayload(
            execution_point="brain.perceive.start",
            bogus_field="x",  # type: ignore[call-arg]
        )
