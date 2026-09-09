"""MultiToolLoopBreakerGate — 5 fixture 行为契约 (ADR-0214 PR-B §5.2).

触发梯子:
1. stuck_progress — confidence 下降 + completed 不增长
2. completed_flatline — completed 不增长 (即使 confidence 持平)
3. fingerprint_static — 最近 K 步工具调用指纹无变化

不触发场景:
- 工具切换 + observation 不同 (real progress)
- TaskProgressProjection 缺失 (fail-open)
- 单工具熔断器也触发的场景 (共存, defense-in-depth)
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
    MultiToolLoopBreakerGate,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    ToolCall,
    Turn,
)
from lca.contracts.models.core.policy.loop_policy import LoopPolicyThresholds
from lca.contracts.models.core.state.state import AgentState, Budget

# ── Fixtures ────────────────────────────────────────────────────────────


@dataclass
class _TurnStub:
    """Minimal stand-in for ``ControlTurnView`` covering what the gate reads."""

    action_type: str = ActionType.USE_TOOL.value
    tool_name: str | None = None
    observation_success: bool | None = None
    tool_arguments: dict | None = None
    observation_payload: object | None = None
    observation_error: str | None = None
    files_created: tuple[str, ...] = ()


def _state_with(
    *,
    projection_attached: bool,
    confidence_history: list[float] | None = None,
    completed_history: list[tuple[str, ...]] | None = None,
    history: tuple[_TurnStub, ...] = (),
) -> AgentState:
    """Build a minimal AgentState carrying the pieces the gate inspects.

    We bypass full AgentState construction because the gate only reads:
      - ``state.task_progress_projection`` (PR-B projection)
      - ``state.control_turns`` (via iter_control_turns_reversed)
    Both are monkey-patched onto a bare AgentState — the gate never touches
    the other AgentState fields.
    """

    state = AgentState(
        trace_id="trace-test",
        task="test-task",
        budget=Budget(max_steps=100),
    )
    if projection_attached:
        from lca.plugins.session.task_progress.projection import (
            TaskProgressProjection,
        )

        projection = TaskProgressProjection()
        # 直接喂合成 completed_history + confidence_history,
        # 避免走完整 fold 链路 — 这里测的是 Gate 读 projection 的逻辑。
        if confidence_history is not None:
            for c in confidence_history:
                projection._confidence_history.append(c)
        if completed_history is not None:
            for snap in completed_history:
                projection._completed_history.append(snap)
        state.task_progress_projection = projection  # type: ignore[attr-defined]
    state.control_turns = list(history)
    return state


def _decision(tool_name: str, **arguments: object) -> Decision:
    return Decision(
        decision_id="dec-test",
        action_type=ActionType.USE_TOOL,
        rationale="test",
        confidence=0.9,
        tool_calls=[
            ToolCall(
                call_id="call-test",
                tool_name=tool_name,
                arguments=dict(arguments),
            )
        ],
    )


def _non_tool_decision() -> Decision:
    return Decision(
        decision_id="dec-test",
        action_type=ActionType.RESPOND,
        rationale="test",
        confidence=0.9,
    )


# ── Fixture 1: 双工具交替失败 → 触发 stuck_progress ─────────────────


@pytest.mark.asyncio
async def test_alternating_two_tools_triggers_stuck_progress():
    """read_skill_reference ↔ runCommand 交替失败: 单工具 breaker 漏判,
    multi-tool 应在 confidence 下降后熔断。"""
    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(progress_warn=3, progress_break=6, break_failures=3)
    )
    # confidence 从 0.6 单调下降到 0.0, completed 一直为空 (没新增)
    state = _state_with(
        projection_attached=True,
        confidence_history=[0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
        completed_history=[()] * 6,
    )
    decision = _decision("read_skill_reference", path="REFERENCE.md", skill_id="officecli")

    out = await gate.enforce(state, decision)

    assert out.action_type == ActionType.RESPOND
    assert "已熔断" in out.response_text
    assert out.degraded_from == ActionType.USE_TOOL


# ── Fixture 2: 单工具反复失败 → 触发 (单工具 breaker 也触发, 共存) ──


@pytest.mark.asyncio
async def test_single_tool_repeated_failure_triggers_multi_tool_too():
    """同一工具连续失败, 单工具 + multi-tool 都触发,验证 defense-in-depth。"""
    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(progress_warn=3, progress_break=6, break_failures=3)
    )
    state = _state_with(
        projection_attached=True,
        confidence_history=[0.5, 0.4, 0.3, 0.2, 0.1, 0.05],
        completed_history=[()] * 6,
    )
    decision = _decision("runCommand", command="officecli create foo.pptx")

    out = await gate.enforce(state, decision)

    assert out.action_type == ActionType.RESPOND
    assert out.degraded_from == ActionType.USE_TOOL


# ── Fixture 3: 工具切换 + observation 不同 → 不触发 ──────────────────


@pytest.mark.asyncio
async def test_real_progress_does_not_trigger():
    """confidence 上升, completed 持续增长 → 不触发。"""
    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(progress_warn=3, progress_break=6, break_failures=3)
    )
    state = _state_with(
        projection_attached=True,
        confidence_history=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        completed_history=[
            (),
            ("step-1",),
            ("step-1", "step-2"),
            ("step-1", "step-2", "step-3"),
            ("step-1", "step-2", "step-3", "step-4"),
            ("step-1", "step-2", "step-3", "step-4", "step-5"),
        ],
    )
    decision = _decision("runCommand", command="officecli add slide")

    out = await gate.enforce(state, decision)

    assert out.action_type == ActionType.USE_TOOL  # 不 rewrite


# ── Fixture 4: stuck 后实际取得进展 → 不触发 ────────────────────────


@pytest.mark.asyncio
async def test_stuck_then_progress_does_not_trigger():
    """前 4 步 stuck, 第 5 步 confidence 跳升, completed 新增 → 不触发。"""
    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(progress_warn=3, progress_break=6, break_failures=3)
    )
    state = _state_with(
        projection_attached=True,
        confidence_history=[0.6, 0.5, 0.4, 0.3, 0.5, 0.7],  # 后两步回升
        completed_history=[
            (),
            (),
            (),
            (),
            ("step-1",),  # 第 5 步新增
            ("step-1", "step-2"),  # 第 6 步新增
        ],
    )
    decision = _decision("runCommand", command="officecli add slide")

    out = await gate.enforce(state, decision)

    assert out.action_type == ActionType.USE_TOOL


# ── Fixture 5: TaskProgressProjection 缺失 → fail-open ──────────────


@pytest.mark.asyncio
async def test_missing_projection_fails_open():
    """projection 缺失 (plugin 未 wire) → 返回原 decision, 不阻塞。"""
    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(progress_warn=3, progress_break=6, break_failures=3)
    )
    state = _state_with(projection_attached=False)
    decision = _decision("runCommand", command="foo")

    out = await gate.enforce(state, decision)

    assert out is decision  # 同一对象, fail-open


# ── Fixture 6: 非 USE_TOOL 决策 → 透传 ──────────────────────────────


@pytest.mark.asyncio
async def test_non_tool_decision_passes_through():
    """RESPOND/STOP/HANDOFF 决策不进入熔断器。"""
    gate = MultiToolLoopBreakerGate()
    state = _state_with(
        projection_attached=True,
        confidence_history=[0.1, 0.1, 0.1, 0.1, 0.1, 0.1],  # 即使 stuck
    )
    out = await gate.enforce(state, _non_tool_decision())

    assert out is not None
    assert out.action_type == ActionType.RESPOND


# ── Fixture 7: completed_flatline (Trigger 2) ──────────────────────


@pytest.mark.asyncio
async def test_completed_flatline_with_steady_confidence_triggers():
    """confidence 持平 (没下降), 但 completed 一直不增长 → 触发 flatline。"""
    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(progress_warn=3, progress_break=6, break_failures=3)
    )
    state = _state_with(
        projection_attached=True,
        confidence_history=[0.5] * 6,  # 完全持平
        completed_history=[()] * 6,  # 不增长
    )
    decision = _decision("readFile", path="/mnt/data/outputs/q4.pptx")

    out = await gate.enforce(state, decision)

    assert out.action_type == ActionType.RESPOND
    assert "completed" in out.response_text or "completed 集合" in out.response_text


# ── Fixture 8: fingerprint_static (Trigger 3) ─────────────────────


@pytest.mark.asyncio
async def test_static_fingerprint_over_recent_turns_triggers():
    """最近 K 步都是 read_skill_reference(officecli, REFERENCE.md),触发 fingerprint_static。"""

    # 构造 3 个相同 tool call + observation 的 Turn
    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(progress_warn=3, progress_break=6, break_failures=3)
    )

    # 不再本地构造 turns — 移到下方统一构造 Turn 序列
    raw_turns = []  # 占位, 见下方 history 注入

    # 注意: confidence_history 不够长 → Trigger 1/2 不触发
    # 但 fingerprint_static 仍可触发 (因为 fingerprint 检查只看 turn)
    # 直接存 Turn 而非 ControlTurnView, 让 control_turns() 走
    # turns_to_control_views 正常路径。
    raw_turns = []
    for _ in range(3):
        decision_obj = Decision(
            decision_id="dec-x",
            action_type=ActionType.USE_TOOL,
            rationale="x",
            confidence=0.5,
            tool_calls=[
                ToolCall(
                    call_id="call-x",
                    tool_name="read_skill_reference",
                    arguments={"path": "REFERENCE.md", "skill_id": "officecli"},
                )
            ],
        )
        observation_obj = Observation(
            observation_id="obs-x",
            success=False,
            payload={"error": "技能 'officecli' 中不存在资源路径 'REFERENCE.md'"},
            error="技能 'officecli' 中不存在资源路径 'REFERENCE.md'",
        )
        raw_turns.append(Turn(decision=decision_obj, observation=observation_obj))

    state = _state_with(
        projection_attached=True,
        confidence_history=[0.5],  # 仅 1 个,不够 progress_break
        history=tuple(raw_turns),
    )
    decision_obj = _decision("read_skill_reference", path="REFERENCE.md", skill_id="officecli")

    out = await gate.enforce(state, decision_obj)

    # 期望:Trigger 3 触发 → rewrite
    assert out.action_type == ActionType.RESPOND


# ── Pure-function unit tests ──────────────────────────────────────────


def test_confidence_history_from_projection_window():
    from lca.plugins.session.task_progress.projection import TaskProgressProjection

    p = TaskProgressProjection()
    for c in [0.1, 0.2, 0.3, 0.4, 0.5]:
        p._confidence_history.append(c)

    from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
        _confidence_history_from_projection,
    )

    assert _confidence_history_from_projection(p, 3) == (0.3, 0.4, 0.5)
    assert _confidence_history_from_projection(p, 10) == (0.1, 0.2, 0.3, 0.4, 0.5)


def test_completed_growth_when_history_too_short_returns_window():
    """history 不足 → 返回 window (fail open, 不阻断真实 progress)。"""
    from lca.plugins.session.task_progress.projection import TaskProgressProjection

    p = TaskProgressProjection()
    from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
        _completed_growth,
    )

    assert _completed_growth(p, 6) == 6  # fail-open


def test_completed_growth_zero_when_no_new_steps():
    from lca.plugins.session.task_progress.projection import TaskProgressProjection

    p = TaskProgressProjection()
    for snap in [("a",), ("a",), ("a",), ("a",)]:
        p._completed_history.append(snap)
    from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
        _completed_growth,
    )

    assert _completed_growth(p, 4) == 0


def test_completed_growth_counts_new_unique_steps():
    from lca.plugins.session.task_progress.projection import TaskProgressProjection

    p = TaskProgressProjection()
    for snap in [(), ("a",), ("a", "b"), ("a", "b", "c")]:
        p._completed_history.append(snap)
    from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
        _completed_growth,
    )

    # 增量: ()→a (+1), a→ab (+1), ab→abc (+1) = 3
    assert _completed_growth(p, 4) == 3


def test_force_respond_preserves_decision_id():
    from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
        _force_respond,
    )

    original = _decision("foo", x=1)
    forced = _force_respond(original, rationale="r", response="resp")

    assert forced.decision_id == original.decision_id
    assert forced.action_type == ActionType.RESPOND
    assert forced.degraded_from == ActionType.USE_TOOL
    assert forced.rationale == "r"
    assert forced.response_text == "resp"


def test_fingerprint_variance_with_empty_turns_returns_one():
    """无 turn → variance=1.0 (fail-open, 不触发 fingerprint_static)。"""
    from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
        _fingerprint_variance_over_turns,
    )

    candidate = ToolCall(call_id="c", tool_name="x", arguments={})
    assert _fingerprint_variance_over_turns([], candidate) == 1.0


def test_multi_tool_break_verdict_is_frozen():
    from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
        MultiToolBreakVerdict,
    )

    v = MultiToolBreakVerdict(
        kind="stuck_progress",
        window=6,
        confidence_delta=-0.3,
        completed_growth=0,
        fingerprint_variance=1.0,
    )
    with pytest.raises((AttributeError, Exception)):
        v.kind = "tampered"  # type: ignore[misc]
