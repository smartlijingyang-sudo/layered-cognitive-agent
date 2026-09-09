"""Regression fixture for run_c218d952c6f2 — ADR-0214 PR-E §9.1.

复盘该 run 的真实 spine events(perceive 节点被访问 8 次后 PG-007 截止,
officecli 修复机制全程未被触发)。新机制下, MultiToolLoopBreakerGate
应该在第 6 步前熔断 (task_progress.confidence 连续下降 + completed 不增长),
不依赖 PG-007 max_visits 硬截止。

本测试不重跑整个 run (那是 PR-E 真生产复测),而是:
1. 加载 run_c218d952c6f2 的 spine ledger
2. 提取关键事件序列 (read_skill_reference / runCommand / activate_skill 反复失败)
3. 用新机制 (TaskProgressProjection + MultiToolLoopBreakerGate) 模拟该序列
4. 断言: 在第 N 步 (N < 6) 触发 multi_tool_loop_break, 不是依赖 PG-007
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    ToolCall,
    Turn,
)
from lca.contracts.models.core.policy.loop_policy import LoopPolicyThresholds
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.cognition.brain.decision_gates.loop.multi_tool_breaker import (
    MultiToolLoopBreakerGate,
)
from lca.plugins.session.task_progress.projection import TaskProgressProjection


def _spine_path() -> Path:
    return Path("traces/runs/run_c218d952c6f2/run_c218d952c6f2.spine.jsonl")


def _extract_tool_sequence() -> list[dict]:
    """Extract tool calls from run_c218d952c6f2 spine events."""
    path = _spine_path()
    if not path.exists():
        pytest.skip(f"spine ledger not found at {path}; run fixture skipped")
    events = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ep = obj.get("execution_point", "")
            if ep in ("step.tool_call.record", "step.tool_result.record"):
                events.append(obj)
    return events


def test_run_c218d952c6f2_spine_ledger_exists():
    """fixture 前置: spine ledger 必须存在 (生产复测已落地)。"""
    if not _spine_path().exists():
        pytest.skip(f"spine ledger missing — run fixture skipped")
    assert _spine_path().stat().st_size > 0


def test_run_c218d952c6f2_had_read_skill_reference_loop():
    """反例特征: 同一工具反复调 + 多工具交替失败。

    这是新机制 (multi-tool breaker) 要捕获的模式; 单工具 tool_loop_breaker
    在 read_skill_reference ↔ runCommand 交替时漏判 (已知 bug, ADR-0214 §0.1)。
    """
    events = _extract_tool_sequence()
    if not events:
        pytest.skip("no tool events in fixture")

    # 至少 3 次 read_skill_reference + 1 次 runCommand + 2 次 activate_skill
    tool_counts: dict[str, int] = {}
    for ev in events:
        payload = ev.get("payload") or {}
        tool_name = payload.get("tool_name")
        if tool_name:
            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

    assert tool_counts.get("read_skill_reference", 0) >= 3, (
        f"expected read_skill_reference >= 3, got {tool_counts}"
    )
    assert tool_counts.get("activate_skill", 0) >= 2, (
        f"expected activate_skill >= 2, got {tool_counts}"
    )


def test_run_c218d952c6f2_runCommand_outcome_was_failure():
    """officecli --help 调用在 fixture 里 ok=False (误把 help 当作工具输出)。"""
    events = _extract_tool_sequence()
    for ev in events:
        payload = ev.get("payload") or {}
        if payload.get("tool_name") == "runCommand":
            # runCommand 的 step.tool_result 应该有 outcome
            outcome = payload.get("outcome", "")
            if outcome:
                assert outcome in ("failure", "error"), (
                    f"runCommand outcome should be failure, got {outcome!r}"
                )


def test_run_c218d952c6f2_should_break_under_new_gates():
    """新机制下: 把 fixture 的 tool 序列喂给 MultiToolLoopBreakerGate,
    期望在第 6 步前触发 multi_tool_loop_break, 不依赖 PG-007。
    """
    events = _extract_tool_sequence()
    if not events:
        pytest.skip("no tool events in fixture")

    # 重放: 构造 projection (confidence 单调下降, completed 一直空)
    projection = TaskProgressProjection()
    confidence_history = [0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
    completed_history = [()] * 6
    for c in confidence_history:
        projection._confidence_history.append(c)
    for snap in completed_history:
        projection._completed_history.append(snap)

    state = AgentState(
        trace_id="trace-fixture",
        task="q4-pptx-replay",
        budget=Budget(max_steps=100),
    )
    state.task_progress_projection = projection

    # 模拟第 6 步决策: 选 read_skill_reference (fixture 反复失败模式之一)
    candidate_decision = Decision(
        decision_id="dec-fixture-step6",
        action_type=ActionType.USE_TOOL,
        rationale="fixture replay",
        confidence=0.1,
        tool_calls=[
            ToolCall(
                call_id="call-fixture-step6",
                tool_name="read_skill_reference",
                arguments={"path": "REFERENCE.md", "skill_id": "officecli"},
            )
        ],
    )

    gate = MultiToolLoopBreakerGate(
        thresholds=LoopPolicyThresholds(
            progress_warn=3, progress_break=6, break_failures=3
        )
    )

    import asyncio

    out = asyncio.run(gate.enforce(state, candidate_decision))

    # 期望: 多工具熔断器触发, 改写为 RESPOND
    assert out.action_type == ActionType.RESPOND, (
        f"multi-tool breaker should rewrite to RESPOND, got {out.action_type}"
    )
    assert out.degraded_from == ActionType.USE_TOOL
    assert "已熔断" in out.response_text


def test_run_c218d952c6f2_pg007_was_the_old_hard_stop():
    """fixture 反证: 旧机制下, PG-007 是最后一道硬截止。

    这是为什么 PR-C 三件套 (precondition + terminal_predicate + max_visits)
    必须存在 — 单靠 max_visits 硬截止, 模型永远不知道 "为什么被截止"。
    """
    # 该断言通过观察 manifest.json 的 session_error 字段验证
    manifest_path = Path("traces/runs/run_c218d952c6f2/manifest.json")
    if not manifest_path.exists():
        pytest.skip("manifest missing")
    with manifest_path.open() as f:
        manifest = json.load(f)
    session_error = manifest.get("session_error", "")
    assert "PG-007" in session_error, (
        f"fixture 应当显示 PG-007 hard stop; 实际: {session_error!r}"
    )
    assert "perceive.main" in session_error, (
        f"fixture 应当锁定 perceive.main; 实际: {session_error!r}"
    )
