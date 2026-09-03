"""Regression tests for SimpleBody.act phase advance contract.

ADR-0169 PR-26 task-25: phase 推进责任钉死在 SimpleBody.act。USE_TOOL /
DELEGATE / HANDOFF → cursor.advance("act");STOP / ASK_HUMAN →
cursor.advance("stop");RESPOND → 不 advance。CursorError 降级 warning,
不让单 decision 失败变 session RuntimeError。

直接根因:run_b61bb9ed5707 在 ``record_tool_call must be in ACT window`` 处
崩;根本原因是 SafeExecutor._open_act_step(改名为 _record_tool_call_evidence)
假设 cursor 已在 act phase,但 imperative 路径下没人 advance。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.cognition.body.simple_body import SimpleBody
from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision, ToolCall
from lca.contracts.models.core.result import UnregisteredActionError
from lca.contracts.models.core.state import AgentState
from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import CursorError
from lca.infrastructure.observability.loop_cursor import StdLoopCursor
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    bind_current_cursor,
    reset_current_cursor,
)


@dataclass
class _StubSpine:
    """Stub WritePort —— 捕获所有 append 调用供 assertion 使用。"""

    records: list[dict[str, Any]] = field(default_factory=list)

    def append(
        self,
        *,
        execution_point: str,
        payload: dict[str, Any],
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int:
        self.records.append(
            {
                "execution_point": execution_point,
                "payload": payload,
                "run_id": run_id,
                "seq": seq,
                "incarnation": incarnation,
                "phase": phase,
            }
        )
        return seq


def _make_cursor_in_think() -> tuple[StdLoopCursor, _StubSpine]:
    """cursor 已 advance 到 think phase (think 是 record_tool_call 的非法 phase)。"""
    spine = _StubSpine()
    cursor = StdLoopCursor(
        spine=spine,
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="solo", incarnation_seq=1),
    )
    cursor.advance("perceive")
    cursor.advance("think")
    return cursor, spine


def _make_decision(action_type: ActionType) -> Decision:
    """构造一个给定 action_type 的 Decision,tool_calls 仅 USE_TOOL 时填一个。"""
    tool_calls: list[ToolCall] = []
    if action_type is ActionType.USE_TOOL:
        tool_calls.append(ToolCall(call_id="t1", tool_name="test_tool", arguments={}))
    return Decision(
        decision_id="dec-1",
        action_type=action_type,
        rationale="test",
        confidence=1.0,
        tool_calls=tool_calls,
    )


def _make_state() -> AgentState:
    """最小可用 AgentState;act() 不读 state 实际内容。"""
    return AgentState(
        trace_id="t1",
        task="test",
        budget=create_budget(max_steps=5),
        step=1,
    )


def _make_dummy_body() -> SimpleBody:
    """SimpleBody 实例 —— 用 None 作依赖因为 act 流程不应触达 registry 解析。"""
    return SimpleBody(
        tool_registry=None,  # type: ignore[arg-type]
        safe_executor=None,  # type: ignore[arg-type]
        transport_registry=None,  # type: ignore[arg-type]
        action_registry=None,  # type: ignore[arg-type]
    )


# ── 1. USE_TOOL decision → cursor.advance("act") ─────────────


@pytest.mark.asyncio
async def test_simple_body_act_use_tool_advances_cursor_to_act_phase() -> None:
    """USE_TOOL decision → SimpleBody.act 入口 advance cursor 到 act phase。

    修复前的症状:record_tool_call 在 think phase 抛 CursorError,session 崩。
    """
    cursor, spine = _make_cursor_in_think()
    assert cursor.snapshot.phase == "think", "fixture must start in think phase"

    token = bind_current_cursor(cursor)
    try:
        body = _make_dummy_body()
        # action_registry=None → AttributeError 或 UnregisteredActionError;
        # 我们只验证 cursor 已 advance 到 act,不验证 handler 执行。
        with pytest.raises((AttributeError, UnregisteredActionError)):
            await body.act(_make_decision(ActionType.USE_TOOL), _make_state())
    finally:
        reset_current_cursor(token)

    assert cursor.snapshot.phase == "act", (
        f"USE_TOOL must advance cursor to act, got {cursor.snapshot.phase!r}"
    )
    phase_eps = [r for r in spine.records if r["execution_point"] == "phase.act.fold"]
    assert len(phase_eps) == 1, f"expected one phase.act.fold EP, got {len(phase_eps)}: {phase_eps}"


# ── 2. RESPOND decision → cursor 留在 think phase ─────────────


@pytest.mark.asyncio
async def test_simple_body_act_respond_does_not_advance_cursor() -> None:
    """RESPOND decision 不 advance;cursor 留在 think phase。

    RESPOND 是认知输出,不是 act phase 的副作用,SimpleBody 不应该把 cursor
    推到 act 或 stop。
    """
    cursor, _ = _make_cursor_in_think()
    assert cursor.snapshot.phase == "think"

    token = bind_current_cursor(cursor)
    try:
        body = _make_dummy_body()
        with pytest.raises((AttributeError, UnregisteredActionError)):
            await body.act(_make_decision(ActionType.RESPOND), _make_state())
    finally:
        reset_current_cursor(token)

    assert cursor.snapshot.phase == "think", (
        f"RESPOND must keep cursor in think, got {cursor.snapshot.phase!r}"
    )


# ── 3. STOP decision → cursor.advance("stop") ─────────────


@pytest.mark.asyncio
async def test_simple_body_act_stop_advances_cursor_to_stop_phase() -> None:
    """STOP decision → cursor advance 到 stop phase。

    stop → perceive 在 std.py 触发新 iteration,符合 L1 iteration 边界。
    """
    cursor, spine = _make_cursor_in_think()
    token = bind_current_cursor(cursor)
    try:
        body = _make_dummy_body()
        with pytest.raises((AttributeError, UnregisteredActionError)):
            await body.act(_make_decision(ActionType.STOP), _make_state())
    finally:
        reset_current_cursor(token)

    assert cursor.snapshot.phase == "stop", (
        f"STOP must advance cursor to stop, got {cursor.snapshot.phase!r}"
    )
    phase_eps = [r for r in spine.records if r["execution_point"] == "phase.stop.fold"]
    assert len(phase_eps) == 1, f"expected one phase.stop.fold EP, got {len(phase_eps)}"


# ── 4. CursorError in advance → SimpleBody 降级 warning,act 不抛 ─────────────


@pytest.mark.asyncio
async def test_simple_body_act_swallows_cursor_advance_error() -> None:
    """cursor 已 closed → advance 抛 CursorError,SimpleBody 必须降级(不传给 caller)。

    Cursor 已经关闭时 advance 抛错是预期 — 因为 cursor.close(reason) 后所有
    advance / record 都被锁住。SimpleBody 必须降级:不让单 decision 失败
    把整个 session 拉成 RuntimeError(这是 run_b61bb9ed5707 的根因)。
    """
    cursor, _ = _make_cursor_in_think()
    cursor.close("completed")

    token = bind_current_cursor(cursor)
    try:
        body = _make_dummy_body()
        # act 应该继续走到 handler.resolve / UnregisteredActionError 路径,
        # 而不是把 CursorError 当作 fatal。
        with pytest.raises((AttributeError, UnregisteredActionError)) as exc_info:
            await body.act(_make_decision(ActionType.USE_TOOL), _make_state())
        # 不是 CursorError 的子类即通过。
        assert not isinstance(exc_info.value, CursorError), (
            f"SimpleBody.act must not propagate CursorError to caller, got {exc_info.value!r}"
        )
    finally:
        reset_current_cursor(token)


# ── 5. 无 cursor 绑定 → SimpleBody 不抛 ─────────────


@pytest.mark.asyncio
async def test_simple_body_act_without_bound_cursor_is_noop_for_phase() -> None:
    """ContextVar 未注入 cursor → SimpleBody 静默跳过 phase advance。

    测试场景(无 run context):act 仍然尝试 handler.resolve → 抛
    UnregisteredActionError(action_type),但不因 cursor 缺失而抛 CursorError。
    """
    # 不 bind cursor
    body = _make_dummy_body()
    with pytest.raises((AttributeError, UnregisteredActionError)) as exc_info:
        await body.act(_make_decision(ActionType.USE_TOOL), _make_state())
    assert not isinstance(exc_info.value, CursorError)


# ── 6. action_type=str(契约)回归锁 — run_3b30e4c5b107 root cause ─────────
#
# 2026-09 ``run_3b30e4c5b10e`` 失败:``RuntimeError("'str' object has no attribute
# 'value'")``。直接原因:``SimpleBody._advance_cursor_for_action(decision.action_type)``
# 内部写 ``CursorRecord.try_advance(target, action_type=action_type.value)``,
# 但 ``Decision.action_type: str``(contracts/models/core/decision.py:69)——
# action_type 是 str 而非 enum,``"respond".value`` 抛 AttributeError,升级
# 成 session RuntimeError。
#
# 修复:签名改成 ``action_type: str``,``.value`` 删掉。本测试用原生 str
# 构造 Decision,锁住契约层 str 的事实,阻止回归。
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simple_body_act_with_str_action_type_does_not_raise_attribute_error() -> None:
    """Decision.action_type 是 str(契约层):直接喂 str 不应抛 AttributeError。

    这是 run_3b30e4c5b10e 的回归锁。修复前 SimpleBody 在 _advance_cursor_for_action
    里写 ``action_type.value``,str 上没有 .value → 整个 session RuntimeError。
    修复后签名 ``action_type: str`` + 直接传 str 给 CursorRecord.try_advance,
    ``_ACTION_TO_PHASE`` 是 ``dict[str, PhaseName]`` 查表,str key 直接命中。
    """
    cursor, _ = _make_cursor_in_think()
    token = bind_current_cursor(cursor)
    try:
        body = _make_dummy_body()
        # 契约层 Decision.action_type: str —— 用原生 str 而非 enum
        raw_str_decision = _make_decision_raw_str("respond")
        # 我们只验证 _advance_cursor_for_action 不抛 AttributeError。
        # action_registry=None 仍然会 AttributeError,但不是 .value 路径的错。
        with pytest.raises((AttributeError, UnregisteredActionError)) as exc_info:
            await body.act(raw_str_decision, _make_state())
        # 关键断言:错误信息不能是 "'str' object has no attribute 'value'"
        assert "value" not in str(exc_info.value) or "no attribute 'value'" not in str(
            exc_info.value
        ), f"str action_type must not trigger .value AttributeError, got {exc_info.value!r}"
    finally:
        reset_current_cursor(token)

    # RESPOND 不在 _ACTION_TO_PHASE 表里 → cursor 应留在 think phase
    assert cursor.snapshot.phase == "think"


@pytest.mark.asyncio
async def test_simple_body_act_with_str_use_tool_advances_to_act() -> None:
    """str action_type='use_tool' → 命中 _ACTION_TO_PHASE[str] → cursor 推到 act。

    验证 _ACTION_TO_PHASE 字典改用 str key 之后,str action_type 能正常查表。
    """
    cursor, _ = _make_cursor_in_think()
    token = bind_current_cursor(cursor)
    try:
        body = _make_dummy_body()
        raw_str_decision = _make_decision_raw_str("use_tool")
        with pytest.raises((AttributeError, UnregisteredActionError)):
            await body.act(raw_str_decision, _make_state())
    finally:
        reset_current_cursor(token)

    assert cursor.snapshot.phase == "act", (
        f"str 'use_tool' must advance to act, got {cursor.snapshot.phase!r}"
    )


def _make_decision_raw_str(action_type: str) -> Decision:
    """用原生 str action_type 构造 Decision —— 模拟契约层 fact。"""
    return Decision(
        decision_id="dec-str-1",
        action_type=action_type,  # type: ignore[arg-type]  # 契约事实
        rationale="str action_type regression test",
        confidence=1.0,
    )
