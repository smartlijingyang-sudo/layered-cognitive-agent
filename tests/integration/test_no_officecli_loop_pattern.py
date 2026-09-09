"""Invariant: 任何 officecli skill 反例都不能"无限循环"。

ADR-0214 §9.2: 任何 run 出现 read_skill_reference 失败 5 步 + activate_skill
反复 3 步 → MultiToolLoopBreaker 必须在 confidence 下降 ≤0.1 时熔断。

本测试不依赖具体 run,而是直接构造 "officecli skill 反例" 场景的
state + projection, 验证 breaker 一定熔断。
"""

from __future__ import annotations

import asyncio

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.models.core.policy.loop_policy import LoopPolicyThresholds
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
    MultiToolLoopBreakerGate,
)
from lca.plugins.session.task_progress.projection import TaskProgressProjection


def _build_officecli_loop_state(
    *,
    confidence_drop: float = 0.5,
    completed_steps: tuple[str, ...] = (),
    n_history: int = 6,
) -> AgentState:
    """Build state with the canonical officecli 反例 projection shape.

    - confidence 从 0.6 下降到 0.6 - confidence_drop
    - completed 始终不变 (flatline)
    - 准备 MultiToolLoopBreakerGate 熔断
    """
    projection = TaskProgressProjection()
    start_conf = 0.6
    end_conf = max(0.0, start_conf - confidence_drop)
    history = [
        start_conf + (end_conf - start_conf) * (i / (n_history - 1))
        for i in range(n_history)
    ]
    for c in history:
        projection._confidence_history.append(c)
    for _ in range(n_history):
        projection._completed_history.append(completed_steps)

    state = AgentState(
        trace_id="trace-inv",
        task="officecli-loop-test",
        budget=Budget(max_steps=100),
    )
    state.task_progress_projection = projection
    return state


@pytest.mark.asyncio
async def test_officecli_loop_pattern_triggers_multi_tool_breaker():
    """invariant: read_skill_reference 失败 5 步 + activate_skill 反复 → 熔断."""
    state = _build_officecli_loop_state(confidence_drop=0.5, completed_steps=())
    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(
            progress_warn=3, progress_break=6, break_failures=3
        )
    )

    # 第 6 步决策: 选 activate_skill (反例典型工具)
    decision = Decision(
        decision_id="dec-invariant",
        action_type=ActionType.USE_TOOL,
        rationale="invariant test",
        confidence=0.1,
        tool_calls=[
            ToolCall(
                call_id="call-invariant",
                tool_name="activate_skill",
                arguments={"skill_id": "officecli"},
            )
        ],
    )

    out = await gate.enforce(state, decision)

    assert out.action_type == ActionType.RESPOND
    assert out.degraded_from == ActionType.USE_TOOL
    assert "已熔断" in out.response_text


@pytest.mark.asyncio
async def test_officecli_loop_with_real_progress_does_not_trigger():
    """invariant 反面: 即使 confidence 下降, 但 completed 持续增长 → 不触发.

    这是关键 — breaker 不能误伤真实进展的 run。"""
    projection = TaskProgressProjection()
    history = [0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
    snapshots = [
        (),
        ("step-1",),
        ("step-1", "step-2"),
        ("step-1", "step-2", "step-3"),
        ("step-1", "step-2", "step-3", "step-4"),
        ("step-1", "step-2", "step-3", "step-4", "step-5"),
    ]
    for c in history:
        projection._confidence_history.append(c)
    for snap in snapshots:
        projection._completed_history.append(snap)

    state = AgentState(
        trace_id="trace-realprog",
        task="real-progress-test",
        budget=Budget(max_steps=100),
    )
    state.task_progress_projection = projection

    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(
            progress_warn=3, progress_break=6, break_failures=3
        )
    )

    decision = Decision(
        decision_id="dec-realprog",
        action_type=ActionType.USE_TOOL,
        rationale="real progress",
        confidence=0.1,
        tool_calls=[
            ToolCall(
                call_id="call-realprog",
                tool_name="runCommand",
                arguments={"command": "officecli add slide"},
            )
        ],
    )

    out = await gate.enforce(state, decision)

    assert out.action_type == ActionType.USE_TOOL, (
        "real progress should not trigger multi-tool breaker"
    )


@pytest.mark.asyncio
async def test_officecli_loop_with_short_history_does_not_trigger():
    """invariant: history 不足 (≤ progress_break) → fail-open 不触发.

    避免对早期 run 误杀。"""
    state = _build_officecli_loop_state(
        confidence_drop=0.5, completed_steps=(), n_history=3
    )
    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(
            progress_warn=3, progress_break=6, break_failures=3
        )
    )

    decision = Decision(
        decision_id="dec-short",
        action_type=ActionType.USE_TOOL,
        rationale="short history",
        confidence=0.3,
        tool_calls=[
            ToolCall(
                call_id="call-short",
                tool_name="read_skill_reference",
                arguments={"path": "REFERENCE.md", "skill_id": "officecli"},
            )
        ],
    )

    out = await gate.enforce(state, decision)

    # history 长度 < progress_break → Trigger 1/2 不满足
    # Trigger 3 (fingerprint_static) 也无 recent turn → fail-open
    assert out.action_type == ActionType.USE_TOOL
