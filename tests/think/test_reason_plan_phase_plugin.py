"""Tests for phase.think.reason.plan plugin (ADR-0217 §3.3 + ADR-0218 §3.3).

think.reason inner_graph 第 1 节点 — 纯 ``build_turn_plan`` 薄壳。

Case 矩阵(spec §3.1):
1. executor 调 ``reasoner.build_turn_plan`` 1 次
2. 返回 NodeOutput 含 ``turn_plan``
3. 注入 None reasoner 返回空
4. 注入 None state 返回空
5. 不调任何 emit 函数(反向断言:模块级不 import emit)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnPlan
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.plugins.think.reason_plan import ThinkReasonPlanExecutor


@dataclass
class _Reasoner:
    plan: ReasonerTurnPlan
    call_count: int = 0

    def build_turn_plan(self, state: AgentState) -> ReasonerTurnPlan:
        self.call_count += 1
        return self.plan


@dataclass
class _StubRuntime:
    state: AgentState | None
    reasoner: Any


def _ctx(caps: dict[str, Any]) -> NodeContext:
    state = AgentState(trace_id="t", task="x", budget=Budget())
    runtime = _StubRuntime(
        state=state,
        reasoner=caps.get("phase.think.reason.plan"),
    )
    return NodeContext(runtime=runtime, budget={}, metadata={})


def _plan() -> ReasonerTurnPlan:
    return ReasonerTurnPlan(
        state_id="t",
        template_id="react",
        decision_path="legacy",
        activated_skill_ids=(),
        tools_count=0,
        available_skills_count=0,
        sections_preview=(),
        variant_preview=None,
    )


@pytest.mark.asyncio
async def test_reason_plan_attaches_turn_plan_port() -> None:
    """Executor 调 ``reasoner.build_turn_plan`` 1 次,返回 NodeOutput 含 turn_plan。"""
    executor = ThinkReasonPlanExecutor()
    reasoner = _Reasoner(plan=_plan())
    result = await executor.node_execute(
        _ctx({"phase.think.reason.plan": reasoner}),
        NodeInput(port_values={}),
    )
    assert reasoner.call_count == 1
    assert result.port_values.get("turn_plan") is reasoner.plan


@pytest.mark.asyncio
async def test_reason_plan_missing_capability_returns_empty_ports() -> None:
    """注入 None reasoner → 返回空 ports。"""
    executor = ThinkReasonPlanExecutor()
    result = await executor.node_execute(_ctx({}), NodeInput(port_values={}))
    assert result.port_values == {}


@pytest.mark.asyncio
async def test_reason_plan_missing_state_returns_empty_ports() -> None:
    """注入 None state(runtime.state=None)→ 返回空 ports。"""
    executor = ThinkReasonPlanExecutor()
    reasoner = _Reasoner(plan=_plan())
    runtime = _StubRuntime(state=None, reasoner=reasoner)
    ctx = NodeContext(runtime=runtime, budget={}, metadata={})
    result = await executor.node_execute(ctx, NodeInput(port_values={}))
    assert result.port_values == {}


def test_reason_plan_module_does_not_import_emit() -> None:
    """反向断言:模块级不 import emit(EP 由 driver 调度,executor 不知道 EP)。"""
    import lca.plugins.think.reason_plan as mod

    src = mod.__file__
    assert src is not None
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "from lca.infrastructure.session.emit" not in text
    assert "from lca.loop.emit" not in text
