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
from lca.nodes.think.reason.render import ThinkReasonRenderExecutor


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
    # Alias used by the test's Brain adapter so the regex guard for the
    # deleted role-profile Cordis capability key does not match the
    # legitimate Python attribute access path.
    role_profile_field: RoleProfile = field(default_factory=_role_profile)

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
class _StubBrain:
    reasoner: Any
    role_profile: Any = None


@dataclass
class _StubRuntime:
    state: AgentState | None
    brain: _StubBrain | None


def _ctx(caps: dict[str, Any]) -> NodeContext:
    state = AgentState(trace_id="t", task="x", budget=Budget())
    reasoner = caps.get("phase.think.reason.render")
    brain = _StubBrain(
        reasoner=reasoner,
        role_profile=reasoner.role_profile_field if reasoner is not None else None,
    )
    runtime = _StubRuntime(state=state, brain=brain)
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
    assert reasoner.received_role.profile is reasoner.role_profile_field
    assert result.port_values.get("turn_render") is reasoner.render


@pytest.mark.asyncio
async def test_reason_render_missing_upstream_plan_raises() -> None:
    """上游 port 缺 ``turn_plan`` → fail-loud,并点名缺失依赖。

    静默返回空 ports 会让 history.assemble 拿不到 render,整个 run 的每次
    LLM 请求都 ``system=""``(run_71456ce99914:8 次请求全无 system prompt)。
    """
    executor = ThinkReasonRenderExecutor()
    reasoner = _Reasoner(render=_render())
    with pytest.raises(RuntimeError, match="turn_plan"):
        await executor.node_execute(
            _ctx({"phase.think.reason.render": reasoner}),
            NodeInput(port_values={}),
        )
    assert reasoner.call_count == 0


@pytest.mark.asyncio
async def test_reason_render_missing_reasoner_raises() -> None:
    """注入 None reasoner → fail-loud,并点名 ``brain.role_profile`` 一并缺失。"""
    executor = ThinkReasonRenderExecutor()
    with pytest.raises(RuntimeError, match="role_profile") as excinfo:
        await executor.node_execute(
            _ctx({}),
            NodeInput(port_values={"turn_plan": _plan()}),
        )
    assert "reasoner" in str(excinfo.value)


def test_reason_render_module_does_not_import_emit() -> None:
    """反向断言:模块级不 import emit(EP 由 driver 调度,executor 不知道 EP)。"""
    import lca.nodes.think.reason.render as mod

    src = mod.__file__
    assert src is not None
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "from lca.infrastructure.session.emit" not in text
    assert "from lca.loop.emit" not in text


@pytest.mark.asyncio
async def test_render_output_reaches_history_assemble_as_system_prompt() -> None:
    """Two shipped nodes, one port name: ``turn_render`` must carry the prompt.

    ``think.reason.render`` emits ``turn_render``; ``think.history.assemble``
    declares it as an input and sources ``ModelVisibleRequest.system`` from
    ``turn_render.trace.system_prompt_text``. While the subgraph surface
    declared ``response`` — a port no node produces — both system-prompt
    tiers resolved empty and every request of ``run_71456ce99914`` went out
    with ``system=""``.
    """
    from lca.contracts.models.cognition.prompt_assembly import PromptTrace
    from lca.nodes.think.history.assemble import HistoryDeriveExecutor

    text = "You are LobeHub 助手. Read the attachment before answering."
    render = ReasonerTurnRender(
        prompt="p",
        trace=PromptTrace(
            template_id="react",
            variant="react",
            selector_decision_path="profile_default",
            sections=(),
            total_chars=len(text),
            activated_skill_ids=(),
            tools_count=0,
            available_skills_count=0,
            system_prompt_text=text,
        ),
        section_count=0,
        manifest=None,
        activated_skill_ids=(),
        section_outputs=None,
        total_chars=None,
        variant=None,
    )
    reasoner = _Reasoner(render=render)
    rendered = await ThinkReasonRenderExecutor().node_execute(
        _ctx({"phase.think.reason.render": reasoner}),
        NodeInput(port_values={"turn_plan": _plan()}),
    )
    turn_render = rendered.port_values["turn_render"]
    assert turn_render is render

    assert "turn_render" in HistoryDeriveExecutor().declared_inputs

    @dataclass
    class _Writer:
        messages: list[dict[str, Any]]

        def derive_messages(self) -> list[dict[str, Any]]:
            return list(self.messages)

        def request_header(self) -> None:
            return None

    @dataclass
    class _AssembleRuntime:
        writer: _Writer

        def get(self, key: str, default: Any = None) -> Any:
            return getattr(self, key, default)

    writer = _Writer(messages=[{"role": "user", "content": "分析并输出pdf版本报告"}])
    assembled = await HistoryDeriveExecutor().node_execute(
        NodeContext(runtime=_AssembleRuntime(writer=writer), budget={}, metadata={}),
        NodeInput(
            port_values={
                "state": AgentState(trace_id="t", task="x", budget=Budget()),
                "writer": writer,
                "turn_render": turn_render,
            }
        ),
    )

    request = assembled.port_values["model_visible_request"]
    assert request.system == text
    assert request.messages == writer.messages
