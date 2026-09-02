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
