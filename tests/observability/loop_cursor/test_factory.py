"""ADR-0169 D8 / PR-25:LoopCursorFactory 测试。

验证 ``LoopCursorFactory.from_profile`` 派生 (StdLoopCursor, Incarnation):
- 派生 cursor 满足 LoopCursor Protocol;snapshot 字段正确填上 run/trace
- Incarnation 显式身份 = (run_id, plan_ref, incarnation_seq=1)
- 派生 cursor 的 incarnation plan_ref 来自 profile.plan_ref

ADR-0068 §决策二(2026-09 重构):plan_ref 必须显式来自 profile,缺字段
**不再 silent fallback 到 ``"default"``** —— 这是身份不是装饰,silent 默认
会把"profile 没装 plan_ref"这种回归藏起来。直接 TypeError 向上抛更安全。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from lca.contracts.observability.incarnation import Incarnation
from lca.infrastructure.observability.loop_cursor import StdLoopCursor
from lca.infrastructure.observability.loop_cursor._spine_port import WritePort
from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory

# ── Stubs ───────────────────────────────────────────────────


@dataclass
class _StubSpine(WritePort):
    """WritePort 协议位最小面;捕获 append 调用 + 返回 seq。"""

    seq_counter: int = 0

    def append(
        self,
        *,
        execution_point: str,
        payload: dict,
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int:
        return seq


@dataclass
class _Profile:
    """duck-typed profile;读 plan_ref 字段(可有可无)。"""

    plan_ref: str = "plan-A"
    observability: dict = field(default_factory=dict)


# ── Tests ───────────────────────────────────────────────────


def test_factory_from_profile_returns_cursor_and_incarnation_pair() -> None:
    """``from_profile`` 返回 ``(StdLoopCursor, Incarnation)`` 二元组。"""
    spine = _StubSpine()
    cursor, incarnation = LoopCursorFactory.from_profile(
        profile=_Profile(plan_ref="plan-A"),
        run_id="r-1",
        trace_id="t-1",
        spine=spine,  # type: ignore[arg-type]
    )

    assert isinstance(cursor, StdLoopCursor)
    assert isinstance(incarnation, Incarnation)
    assert cursor.snapshot.run_id == "r-1"
    assert cursor.snapshot.trace_id == "t-1"
    assert cursor.snapshot.incarnation == 1


def test_factory_incarnation_uses_profile_plan_ref() -> None:
    """``Incarnation.plan_ref`` 来自 ``profile.plan_ref``(直接读,无 duck-type 兜底)。

    ADR-0068 §决策二:plan_ref 是 cursor 的显式身份,不能 silent 默认。
    profile 必须显式提供 ``plan_ref`` 字段;缺则向上抛清晰 TypeError,
    便于 ``RunSessionBuilder._compute_plan_ref`` 的回归立刻暴露。
    """
    # 显式 plan_ref → 透传
    spine = _StubSpine()
    _, inc = LoopCursorFactory.from_profile(
        profile=_Profile(plan_ref="plan-B"),
        run_id="r-2",
        trace_id="t-2",
        spine=spine,  # type: ignore[arg-type]
    )
    assert inc.plan_ref == "plan-B"
    assert inc.run_id == "r-2"
    assert inc.incarnation_seq == 1


def test_factory_raises_when_profile_missing_plan_ref() -> None:
    """profile 缺 plan_ref 字段 → TypeError,不再 silent fallback。

    这是 ADR-0068 §决策二的回归锁:任何在 factory 路径重新引入
    ``getattr(profile, "plan_ref", "default")`` 的提交都会让本测试 fail。
    """
    @dataclass
    class _NoPlanRef:
        observability: dict = field(default_factory=dict)

    spine = _StubSpine()
    with pytest.raises(TypeError, match="profile.plan_ref"):
        LoopCursorFactory.from_profile(
            profile=_NoPlanRef(),  # type: ignore[arg-type]
            run_id="r-3",
            trace_id="t-3",
            spine=spine,  # type: ignore[arg-type]
        )


def test_factory_cursor_satisfies_loop_cursor_protocol() -> None:
    """派生 cursor 满足 ``LoopCursor`` Protocol 契约面(snapshot + advance)。"""
    cursor, _ = LoopCursorFactory.from_profile(
        profile=_Profile(),
        run_id="r-4",
        trace_id="t-4",
        spine=_StubSpine(),  # type: ignore[arg-type]
    )
    # Protocol 不带 runtime_checkable —— 直接验证契约面
    assert hasattr(cursor, "snapshot")
    assert hasattr(cursor, "advance")
    assert hasattr(cursor, "record_thinking")
    assert hasattr(cursor, "record_tool_call")
    assert hasattr(cursor, "record_tool_result")
    assert hasattr(cursor, "record_request_header")
    assert hasattr(cursor, "halt")
    assert hasattr(cursor, "close")
    assert hasattr(cursor, "fork")
    # snapshot.phase 默认 None(OUTSIDE_LOOP;ADR-0169 I-CURSOR-2)
    assert cursor.snapshot.phase is None
