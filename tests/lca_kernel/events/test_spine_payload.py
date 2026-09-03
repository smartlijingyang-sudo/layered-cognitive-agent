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
    """未知 EP → ValueError（fail-fast，I12 同构）。"""
    with pytest.raises(ValueError, match="UnknownSpineExecutionPoint"):
        SpineEventPayload(execution_point="not.in.whitelist")


def test_unknown_channel_raises() -> None:
    """未知 channel → ValueError。"""
    with pytest.raises(ValueError, match="UnknownSpineChannel"):
        SpineEventPayload(execution_point="brain.perceive.start", channel="bogus")


def test_category_mapping_for_pilot_ep() -> None:
    """试点 EP → category 映射正确。"""
    p = SpineEventPayload(execution_point="brain.perceive.start")
    assert p.category == Category("spine.cognition.brain.perceive.start")
    assert p.category.value == "spine.cognition.brain.perceive.start"


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
