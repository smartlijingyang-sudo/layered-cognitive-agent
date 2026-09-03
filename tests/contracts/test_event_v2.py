"""ADR-0179 试点：事件 v2 契约层单元测试（pydantic payload 版）。

覆盖：
- EventCategory 是闭集枚举（E1）；
- EventPayload / DelegationCacheHit 是 pydantic BaseModel（业务方构造 typed）；
- default_plane 与 EventCategory 一一对应；
- PILOT_PAYLOADS 与 PILOT_CATEGORIES 一致；
- publish 模块函数未 boot 时返回 None。
"""

from __future__ import annotations

from enum import Enum

import pytest
from pydantic import ValidationError

from lca.contracts.event_v2 import (
    PILOT_CATEGORIES,
    PILOT_PAYLOADS,
    DelegationCacheHit,
    EventCategory,
    EventPayload,
    EventPlane,
    default_plane,
    publish,
)


def test_event_category_is_close_set() -> None:
    """E1：闭集枚举，不允许外部追加值。"""
    assert isinstance(EventCategory.TEAM_DELEGATION, EventCategory)
    assert EventCategory.TEAM_DELEGATION.value == "team.delegation"
    assert len(EventCategory) == 16


def test_payload_is_pydantic_basemodel() -> None:
    """业务方构造的是 pydantic BaseModel（typed 字段）。"""
    assert issubclass(EventPayload, object)
    assert issubclass(DelegationCacheHit, EventPayload)
    assert issubclass(DelegationCacheHit, object)


def test_pilot_payload_has_required_fields() -> None:
    """DelegationCacheHit 字段名集合与旧 dataclass 对齐：callee_role/subtask_preview/step。"""
    fields = DelegationCacheHit.model_fields
    assert "callee_role" in fields
    assert "subtask_preview" in fields
    assert "step" in fields
    assert "category" in fields


def test_delegation_cache_hit_construction() -> None:
    """业务方一行构造 payload（typed）。"""
    p = DelegationCacheHit(callee_role="analyst", subtask_preview="汇总", step=3)
    assert p.callee_role == "analyst"
    assert p.subtask_preview == "汇总"
    assert p.step == 3
    assert p.category is EventCategory.TEAM_DELEGATION


def test_delegation_cache_hit_rejects_missing_field() -> None:
    """pydantic 字段必填；缺失 = ValidationError，业务方早失败。"""
    with pytest.raises(ValidationError):
        DelegationCacheHit(callee_role="analyst")  # type: ignore[call-arg]


def test_delegation_cache_hit_rejects_extra_field() -> None:
    """extra='forbid'：未知字段拒绝。"""
    with pytest.raises(ValidationError):
        DelegationCacheHit(  # type: ignore[call-arg]
            callee_role="analyst",
            subtask_preview="汇总",
            step=3,
            rogue="no",
        )


def test_default_plane_for_team_delegation() -> None:
    """TEAM_DELEGATION 默认是 STRUCTURAL plane。"""
    assert default_plane(EventCategory.TEAM_DELEGATION) is EventPlane.STRUCTURAL


def test_default_plane_raises_for_unmapped() -> None:
    """未登记的 category → ValueError。"""

    class _FakeCategory(str, Enum):
        DUMMY = "dummy"

    with pytest.raises(ValueError, match="未登记 plane 映射"):
        default_plane(_FakeCategory.DUMMY)  # type: ignore[arg-type]


def test_pilot_payloads_and_categories_aligned() -> None:
    """PILOT_PAYLOADS 与 PILOT_CATEGORIES 派生一致。"""
    assert len(PILOT_PAYLOADS) == 1
    assert frozenset({EventCategory.TEAM_DELEGATION}) == PILOT_CATEGORIES


def test_publish_returns_none_when_sender_not_installed() -> None:
    """未 boot：业务方调 publish 不抛异常，返回 None。"""
    # 强制清空（防止其它测试 set_active_sender 残留）。
    from lca.plugins.events.sender import set_active_sender

    set_active_sender(None)
    result = publish(DelegationCacheHit(callee_role="x", subtask_preview="y", step=0))
    assert result is None


def test_payload_is_frozen() -> None:
    """pydantic frozen=True：业务方构造后不可改。"""
    p = DelegationCacheHit(callee_role="x", subtask_preview="y", step=1)
    with pytest.raises(ValidationError):
        p.callee_role = "z"  # type: ignore[misc]
