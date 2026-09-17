"""Tests for ADR-0220 §6 P4 — concept.prompt.render graph + typed render_turn.

Case 矩阵(ADR-0220 §6.1 / §3.3 / §0.4 N10):
1. ``PromptReasoner.render_turn`` 签名 = ``(context, template, role) -> ReasonerTurnRender``
2. ``render_turn`` 不读 ``AgentState``(manifest 只来自 typed ``ReasonerContext``,
   原样透传到 ``ReasonerTurnRender.manifest``)
3. ``reasoner.py`` 行数 ≤ 280(N10)
4. ``reasoner.py`` 方法 def 数 = 4(__init__ + render_turn + _render_with_template + complete_turn)
5. ``render_turn`` 拒绝空 template_id 当 selector 也没接
6. ``render_turn`` 拒绝 template_provider 缺失
7. ``prompt.sections.assemble`` 节点:typed ``TemplateSelection`` → ``PromptTemplate``
9. ``prompt.sections.fill`` 节点:typed DTO 三元组 → ``(prompt, trace)``
10. ``prompt.trace.compile`` 节点:``(prompt, trace)`` → ``ReasonerTurnRender``
11. ``bundles/concept/prompt_render.yaml`` 拓扑 = 3 节点 + 2 边
12. graph id 闭集前缀 ``concept.``,节点 id 第一段在 N9 action-domain 闭集
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

import pytest
import yaml

from lca.cognition.brain.reasoner.reasoner import PromptReasoner
from lca.contracts.models.cognition.boundary import (
    ReasonerContext,
    RoleSnapshot,
    TemplateSelection,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplate,
    PromptTemplateProvider,
    PromptTrace,
    PureSection,
    SectionOutput,
    SectionReference,
    SectionTrace,
)
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnRender
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.concept.prompt_render.assemble import (
    PromptSectionsAssembleExecutor,
)
from lca.nodes.concept.prompt_render.compile import (
    PromptTraceCompileExecutor,
)
from lca.nodes.concept.prompt_render.fill import PromptSectionsFillExecutor

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_PATH = REPO_ROOT / "bundles" / "concept" / "prompt_render.yaml"
REASONER_PATH = REPO_ROOT / "lca" / "cognition" / "brain" / "reasoner" / "reasoner.py"


@dataclass
class _StubLLM(LLMAdapter):
    async def invoke(self, **_: object) -> object:
        raise NotImplementedError


def _role_profile() -> RoleProfile:
    return RoleProfile(
        role="assistant",
        goal="answer",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _template() -> PromptTemplate:
    return PromptTemplate(
        id="react_prompt",
        variant="react",
        sections=(SectionReference(name="role", kind="pure", optional=False),),
    )


@dataclass
class _StaticRole(PureSection):
    name: str = "role"

    def render(self, *, role_profile: RoleProfile, tools: object) -> SectionOutput:
        return SectionOutput(text="ROLE_BLOCK")


@dataclass
class _Provider:
    template: PromptTemplate

    def get_template(self, template_id: str) -> PromptTemplate | None:
        return self.template if template_id == self.template.id else None

    def list_templates(self) -> tuple[tuple[str, PromptTemplate], ...]:
        return ((self.template.id, self.template),)


def _context() -> ReasonerContext:
    return ReasonerContext(task="hi", activated_skills=(), manifest=None)


def _selection() -> TemplateSelection:
    return TemplateSelection(
        template_id="react_prompt",
        variant="react",
        decision_path="profile_default",
    )


def _role_snapshot() -> RoleSnapshot:
    return RoleSnapshot(profile=_role_profile(), team_awareness=None)


# ── PromptReasoner.render_turn signature + behavior ─────────────────


def test_render_turn_signature_matches_p4_dto_contract() -> None:
    """``render_turn`` 接受 3 个 typed boundary DTO,返回 ``ReasonerTurnRender``。

    实际内容渲染依赖 boot-time 注册的 ``PromptSectionRegistry``,本测试只
    验证签名契约(3 typed DTOs → typed DTO 输出)。section 渲染的 happy-path
    集成由 ``test_prompt_sections_fill_renders_prompt_and_trace`` 覆盖。
    """
    reasoner = PromptReasoner(
        llm=_StubLLM(),
        template_provider=_Provider(_template()),
        section_registry=_StubRegistry(),
    )
    render = reasoner.render_turn(_context(), _selection(), _role_snapshot())
    assert isinstance(render, ReasonerTurnRender)
    # ReasonerTurnRender fields are typed + frozen; spot-check the typed surface.
    assert isinstance(render.section_count, int)
    assert render.variant == "react"
    assert render.activated_skill_ids == ()


def test_render_turn_passes_the_context_manifest_through_untouched() -> None:
    """``render_turn`` 的 manifest 只来自 typed ``ReasonerContext``,原样透传。

    ``complete_turn`` 把它交给 ``CurrentReasonerPrompt.context_manifest``,
    journal 的 ``context_manifest`` 由这一路供给;在这里丢弃它会让 section
    渲染退化成空且无可观测痕迹(run_e204465f48d6)。
    """
    manifest = ContextManifest(
        items=(ContextItem(kind="clock", payload="2026-09-17 Thursday", provenance="clock_sensor"),)
    )
    context = ReasonerContext(task="hi", activated_skills=(), manifest=manifest)
    reasoner = PromptReasoner(
        llm=_StubLLM(),
        template_provider=_Provider(_template()),
        section_registry=_StubRegistry(),
    )
    render = reasoner.render_turn(context, _selection(), _role_snapshot())
    assert render.manifest is manifest


def test_render_turn_rejects_empty_template_without_selector() -> None:
    """空 ``template_id`` + 无 selector → RuntimeError,不静默回退。"""
    reasoner = PromptReasoner(
        llm=_StubLLM(),
        template_provider=_Provider(_template()),
    )
    empty_selection = TemplateSelection(
        template_id="",
        variant="react",
        decision_path="profile_default",
    )
    with pytest.raises(RuntimeError, match="PromptTemplateSelector"):
        reasoner.render_turn(_context(), empty_selection, _role_snapshot())


def test_render_turn_rejects_missing_template_provider() -> None:
    """无 ``template_provider`` → RuntimeError,显式不接。"""
    reasoner = PromptReasoner(llm=_StubLLM())
    with pytest.raises(RuntimeError, match="template_provider"):
        reasoner.render_turn(_context(), _selection(), _role_snapshot())


# ── Bug fix: empty system prompt when registry unwired (regression) ──


@dataclass
class _StubRegistry:
    """Minimal PromptSectionRegistry stub that resolves one section to non-empty text."""

    def register(self, section: object, *, kind: str, name: str) -> None:
        raise AssertionError("stub registry rejects registration")

    def resolve(self, *, kind: str, name: str) -> object | None:
        if (kind, name) == ("pure", "role"):
            return _StaticRole()
        return None

    def list_sections(self) -> tuple[tuple[str, str, object], ...]:
        return (("pure", "role", _StaticRole()),)


def test_render_turn_emits_non_empty_system_prompt_when_registry_wired() -> None:
    """Reasoner 接受 section registry 时,渲染的 ``system_prompt_text`` 非空。

    Regression for the empty-system-prompt defect: tool-using runs ended
    with ``budget_exceeded`` because ``render_template`` was called with
    ``registry=None`` and produced ``system_prompt_text == ""``. Wiring the
    registry at boot must produce a real system prompt so the LLM has a
    stop rule and can converge inside ``think.main max_visits=2``.
    """
    from lca.contracts.models.cognition.prompt_assembly import PromptSectionRegistry

    assert isinstance(_StubRegistry(), PromptSectionRegistry)  # Protocol shape

    reasoner = PromptReasoner(
        llm=_StubLLM(),
        template_provider=_Provider(_template()),
        section_registry=_StubRegistry(),
    )
    render = reasoner.render_turn(_context(), _selection(), _role_snapshot())
    assert render.trace is not None
    assert render.trace.system_prompt_text != "", (
        "reasoner.render_turn produced empty system_prompt_text even with "
        "a section registry wired; the LLM sees no stop rule and overruns "
        "think.main max_visits=2 on every tool-using run."
    )


# ── File-shape invariants (ADR §6.1 / N10) ────────────────────────


def test_reasoner_file_line_count_under_280() -> None:
    """N10:``reasoner.py`` 行数 ≤ 280。"""
    line_count = sum(1 for _ in REASONER_PATH.open(encoding="utf-8"))
    assert line_count <= 280, (
        f"ADR-0220 §6 N10 violated: reasoner.py has {line_count} lines (max 280)."
    )


def test_reasoner_method_def_count_is_four() -> None:
    """N10:PromptReasoner 类方法 def 数 = 4(__init__ + build_turn_plan + render_turn + complete_turn)。"""
    text = REASONER_PATH.read_text(encoding="utf-8")
    method_defs = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("    def ") or line.startswith("    async def ")
    ]
    assert len(method_defs) == 4, (
        f"ADR-0220 §6 N10 violated: PromptReasoner has {len(method_defs)} method "
        f"defs, expected 4. Methods: {method_defs}"
    )


def test_reasoner_has_no_legacy_dead_path() -> None:
    """N10 衍生:``reasoner.py`` 不能再出现 ``_resolve_tools`` / ``_legacy_*`` / ``_tools_service``。"""
    text = REASONER_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "_resolve_tools",
        "_legacy_templates",
        "_tools_service",
        "bind_boot_capabilities",
        "self._tools",
        "self.role_profile",
    ):
        assert forbidden not in text, (
            f"ADR-0220 §6.2 violated: '{forbidden}' still present in reasoner.py."
        )


# ── concept.prompt.render node executors ────────────────────────────


@dataclass
class _StubRuntime:
    tools_provider: object | None = None


def _node_ctx() -> NodeContext:
    return NodeContext(runtime=_StubRuntime(), budget={}, metadata={})


def _assemble_input(
    selection: TemplateSelection | None = None,
    *,
    provider: PromptTemplateProvider | None = None,
) -> NodeInput:
    port_values: dict[str, Any] = {"template_selection": selection or _selection()}
    if provider is not None:
        port_values["prompt_template_provider"] = provider
    return NodeInput(port_values=port_values)


@pytest.mark.asyncio
async def test_prompt_sections_assemble_returns_prompt_template() -> None:
    """typed ``TemplateSelection`` → ``PromptTemplate``。"""
    provider = _Provider(_template())
    executor = PromptSectionsAssembleExecutor()
    result = await executor.node_execute(
        _node_ctx(),
        _assemble_input(provider=provider),
    )
    template = result.port_values.get("prompt_template")
    assert isinstance(template, PromptTemplate)
    assert template.id == "react_prompt"


@pytest.mark.asyncio
async def test_prompt_sections_assemble_rejects_missing_provider() -> None:
    """缺 ``prompt_template_provider`` typed port → RuntimeError。"""
    executor = PromptSectionsAssembleExecutor()
    with pytest.raises(RuntimeError, match="prompt_template_provider"):
        await executor.node_execute(
            _node_ctx(),
            _assemble_input(),
        )


@pytest.mark.asyncio
async def test_prompt_sections_fill_renders_prompt_and_trace() -> None:
    """typed DTO 三元组 → ``(prompt_text, PromptTrace)``。"""
    template = _template()
    role_section = _StaticRole()
    registry = type(
        "_R",
        (),
        {
            "resolve": lambda self, *, kind, name: (
                role_section if (name, kind) == ("role", "pure") else None
            ),
            "list_sections": lambda self: (("pure", "role", role_section),),
            "register": lambda self, *_, **__: None,
        },
    )()
    executor = PromptSectionsFillExecutor()
    result = await executor.node_execute(
        _node_ctx(),
        NodeInput(
            port_values={
                "prompt_template": template,
                "context": _context(),
                "role": _role_snapshot(),
                "prompt_section_registry": registry,
            }
        ),
    )
    text = result.port_values.get("prompt_text")
    trace = result.port_values.get("prompt_trace")
    assert text == "ROLE_BLOCK"
    assert isinstance(trace, PromptTrace)
    assert trace.template_id == "react_prompt"
    assert len(trace.sections) == 1


@pytest.mark.asyncio
async def test_prompt_sections_fill_rejects_bad_inputs() -> None:
    """``context`` / ``role`` / ``prompt_template`` 缺或类型错 → TypeError。"""
    executor = PromptSectionsFillExecutor()
    with pytest.raises(TypeError, match="prompt_template"):
        await executor.node_execute(
            _node_ctx(),
            NodeInput(
                port_values={
                    "prompt_template": "not-a-template",
                    "context": _context(),
                    "role": _role_snapshot(),
                }
            ),
        )


@pytest.mark.asyncio
async def test_prompt_trace_compile_emits_reasoner_turn_render() -> None:
    """``(prompt_text, PromptTrace)`` → ``ReasonerTurnRender`` typed boundary。"""
    trace = PromptTrace(
        template_id="react_prompt",
        variant="react",
        selector_decision_path="profile_default",
        sections=(
            SectionTrace(
                name="role",
                kind="pure",
                optional=False,
                used_fallback=False,
                skipped_empty=False,
                text_chars=10,
                text="ROLE_BLOCK",
            ),
        ),
        total_chars=10,
        activated_skill_ids=(),
        tools_count=0,
        available_skills_count=0,
        system_prompt_text="ROLE_BLOCK",
    )
    executor = PromptTraceCompileExecutor()
    result = await executor.node_execute(
        _node_ctx(),
        NodeInput(port_values={"prompt_text": "ROLE_BLOCK", "prompt_trace": trace}),
    )
    render = result.port_values.get("render")
    assert isinstance(render, ReasonerTurnRender)
    assert render.section_count == 1
    assert render.section_outputs is not None
    assert render.section_outputs[0]["name"] == "role"
    assert render.section_outputs[0]["content_digest"] is not None


@pytest.mark.asyncio
async def test_prompt_trace_compile_handles_none_trace() -> None:
    """``prompt_trace=None`` → 0-section ``ReasonerTurnRender``。"""
    executor = PromptTraceCompileExecutor()
    result = await executor.node_execute(
        _node_ctx(),
        NodeInput(port_values={"prompt_text": "x", "prompt_trace": None}),
    )
    render = result.port_values.get("render")
    assert isinstance(render, ReasonerTurnRender)
    assert render.section_count == 0
    assert render.section_outputs is None


# ── bundles/concept/prompt_render.yaml topology ─────────────────────


def test_prompt_render_bundle_topology() -> None:
    """3 节点 + 2 边,graph id = ``concept.prompt.render``。"""
    data = yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))
    assert data["id"] == "concept.prompt.render"
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2
    node_ids = {n["id"] for n in data["nodes"]}
    assert node_ids == {
        "prompt.sections.assemble",
        "prompt.sections.fill",
        "prompt.trace.compile",
    }
    edge_pairs = {(e["source"], e["target"]) for e in data["edges"]}
    assert edge_pairs == {
        ("prompt.sections.assemble", "prompt.sections.fill"),
        ("prompt.sections.fill", "prompt.trace.compile"),
    }


def test_prompt_render_bundle_uses_three_tier_prefix() -> None:
    """graph id 前缀闭集:``concept.`` 是 ADR §3.3 命名空间。"""
    data = yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))
    prefix = data["id"].split(".", 1)[0] + "."
    assert prefix == "concept."


# silence unused-import warning for field (kept for dataclass extension)
_ = field
