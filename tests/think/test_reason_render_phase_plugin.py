"""Tests for phase.think.reason.render plugin (ADR-0217 §3.3 + ADR-0218 §3.3).

think.reason inner_graph 第 2 节点 — adapter (state, plan) → typed DTOs
→ ``render_turn``(ADR-0220 P4)。

Case 矩阵(spec §3.1):
1. executor 调 ``reasoner.render_turn`` 1 次,带 typed (context, template, role)
2. 上游 port 缺 ``turn_plan`` 返回空
3. 注入 None reasoner 返回空
4. 不调任何 emit 函数(反向断言:模块级不 import emit)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.models.cognition.boundary import (
    ReasonerContext,
    RoleSnapshot,
    TemplateSelection,
)
from lca.contracts.models.cognition.reasoner_turn import (
    ReasonerTurnPlan,
    ReasonerTurnRender,
)
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.plugins.think.reason.render import ThinkReasonRenderExecutor


def _role_profile() -> RoleProfile:
    return RoleProfile(
        role="assistant",
        goal="answer",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


@dataclass
class _Reasoner:
    render: ReasonerTurnRender
    call_count: int = 0
    received_context: ReasonerContext | None = None
    received_template: TemplateSelection | None = None
    received_role: RoleSnapshot | None = None
    role_profile: RoleProfile = field(default_factory=_role_profile)

    def render_turn(
        self,
        context: ReasonerContext,
        template: TemplateSelection,
        role: RoleSnapshot,
    ) -> ReasonerTurnRender:
        self.call_count += 1
        self.received_context = context
        self.received_template = template
        self.received_role = role
        return self.render


@dataclass
class _StubRuntime:
    state: AgentState | None
    reasoner: Any


def _ctx(caps: dict[str, Any]) -> NodeContext:
    state = AgentState(trace_id="t", task="x", budget=Budget())
    runtime = _StubRuntime(
        state=state,
        reasoner=caps.get("phase.think.reason.render"),
    )
    return NodeContext(runtime=runtime, budget={}, metadata={})


def _plan() -> ReasonerTurnPlan:
    return ReasonerTurnPlan(
        state_id="t",
        template_id="react",
        decision_path="profile_default",
        activated_skill_ids=(),
        tools_count=0,
        available_skills_count=0,
        sections_preview=(),
        variant_preview="react",
    )


def _render() -> ReasonerTurnRender:
    return ReasonerTurnRender(
        prompt="p",
        trace=None,
        section_count=0,
        manifest=None,
        activated_skill_ids=(),
        section_outputs=None,
        total_chars=None,
        variant=None,
    )


@pytest.mark.asyncio
async def test_reason_render_attaches_turn_render_port() -> None:
    """Executor 调 ``reasoner.render_turn(context, template, role)`` 1 次,返回 turn_render。"""
    executor = ThinkReasonRenderExecutor()
    reasoner = _Reasoner(render=_render())
    plan = _plan()
    result = await executor.node_execute(
        _ctx({"phase.think.reason.render": reasoner}),
        NodeInput(port_values={"turn_plan": plan}),
    )
    assert reasoner.call_count == 1
    assert reasoner.received_template is not None
    assert reasoner.received_template.template_id == "react"
    assert reasoner.received_role is not None
    assert reasoner.received_role.profile is reasoner.role_profile
    assert result.port_values.get("turn_render") is reasoner.render


@pytest.mark.asyncio
async def test_reason_render_missing_upstream_plan_returns_empty_ports() -> None:
    """上游 port 缺 ``turn_plan`` → 返回空 ports(铁律 2:缺失输入 = 空 NodeOutput)。"""
    executor = ThinkReasonRenderExecutor()
    reasoner = _Reasoner(render=_render())
    result = await executor.node_execute(
        _ctx({"phase.think.reason.render": reasoner}),
        NodeInput(port_values={}),
    )
    assert reasoner.call_count == 0
    assert result.port_values == {}


@pytest.mark.asyncio
async def test_reason_render_missing_capability_returns_empty_ports() -> None:
    """注入 None reasoner → 返回空 ports。"""
    executor = ThinkReasonRenderExecutor()
    result = await executor.node_execute(
        _ctx({}),
        NodeInput(port_values={"turn_plan": _plan()}),
    )
    assert result.port_values == {}


def test_reason_render_module_does_not_import_emit() -> None:
    """反向断言:模块级不 import emit(EP 由 driver 调度,executor 不知道 EP)。"""
    import lca.plugins.think.reason.render as mod

    src = mod.__file__
    assert src is not None
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "from lca.infrastructure.session.emit" not in text
    assert "from lca.loop.emit" not in text
