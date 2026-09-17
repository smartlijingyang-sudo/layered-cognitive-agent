"""PromptAssembler integration — production wiring with real registry + provider.

This test deliberately constructs ``_RegistryImpl``, ``_ProviderImpl``, the
section classes from ``lca.plugins.prompts.sections``, and
``SectionManifestPromptAssembler`` directly. No test-only helpers that
mock production wiring.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from lca.cognition.brain.reasoner.reasoner import PromptReasoner
from lca.cognition.brain.sections.assembler import (
    SectionManifestPromptAssembler,
    render_template,
)
from lca.cognition.member_status import InMemoryMemberStatus
from lca.contracts.atoms.enums.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplate,
    SectionReference,
)
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.perceive.projection import PerceiveProjection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.delegation.delegation import DelegationResult
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.team.awareness import ConsultDuty, TeamAwareness
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.prompts.registry import _RegistryImpl
from lca.plugins.prompts.sections import (
    ActivatedSkillsSection,
    AssignedRolesSection,
    AvailableSkillsSection,
    BackstorySection,
    ContextSection,
    CurrentDateSection,
    EvidencePackSection,
    GoalSection,
    HierarchicalInstructionsSection,
    MemberReportsSection,
    MemberStatusSection,
    ReactToolUsageSection,
    ReactWorkflowSection,
    RoleSection,
    RoutingInstructionsSection,
    TaskSection,
    TeammatesSection,
    ToolsSection,
)
from lca.plugins.prompts.selector import TeamAwarenessTemplateSelector
from lca.plugins.prompts.template_provider import (
    _builtin_templates,
    _ProviderImpl,
)
from lca_kernel.events.bus.bus import EventBus
from lca_kernel.events.test.catalog import build_test_bus


@dataclass(frozen=True)
class _FakeTool:
    name: str
    description: str = ""


def _profile(role: str = "lead") -> RoleProfile:
    return RoleProfile(
        role=role,
        goal=f"goal of {role}",
        backstory=f"backstory of {role}",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _empty_state(*, team_awareness: TeamAwareness | None = None) -> AgentState:
    return AgentState(
        trace_id="t",
        task="probe",
        budget=Budget(),
        team_awareness=team_awareness,
    )


def _registry_with_builtins() -> _RegistryImpl:
    """Build a registry exactly as production code does at boot time."""

    registry = _RegistryImpl()
    # Pure sections
    registry.register(RoleSection(), kind="pure", name="role")
    registry.register(GoalSection(), kind="pure", name="goal")
    registry.register(BackstorySection(), kind="pure", name="backstory")
    registry.register(
        ToolsSection(catalog_tools_xml_provider=lambda: '<tool name="x">x</tool>'),
        kind="stateful",
        name="tools",
    )
    registry.register(
        AvailableSkillsSection(catalog_skills_provider=lambda: "（无技能库）"),
        kind="pure",
        name="available_skills",
    )
    registry.register(ReactWorkflowSection(text="<workflow/>"), kind="pure", name="react_workflow")
    registry.register(
        ReactToolUsageSection(text="<usage/>"), kind="pure", name="react_tool_usage_guidelines"
    )
    registry.register(
        RoutingInstructionsSection(text="routing-rules"), kind="pure", name="routing_instructions"
    )
    registry.register(
        HierarchicalInstructionsSection(text="hier-rules"),
        kind="pure",
        name="hierarchical_instructions",
    )
    # Stateful sections
    registry.register(CurrentDateSection(), kind="stateful", name="current_date")
    registry.register(TaskSection(), kind="stateful", name="task")
    registry.register(ActivatedSkillsSection(), kind="stateful", name="activated_skills")
    registry.register(ContextSection(), kind="stateful", name="context")
    registry.register(TeammatesSection(), kind="stateful", name="teammates")
    registry.register(AssignedRolesSection(), kind="stateful", name="assigned_roles_text")
    registry.register(MemberReportsSection(), kind="stateful", name="member_reports_text")
    registry.register(MemberStatusSection(), kind="stateful", name="member_status_text")
    registry.register(EvidencePackSection(), kind="stateful", name="evidence_pack_text")
    return registry


# ── tests ──────────────────────────────────────────────────────────


class _FakePublishSession:
    """最小测试 Session:只收 append,不投递。"""

    def append(
        self,
        event_type: Any,
        data: Any,
        *,
        producer: Any = None,
        actor: Any = None,
        visibility: Any = None,
        **kwargs: Any,
    ) -> Any:
        del event_type, data, producer, actor, visibility, kwargs
        from types import SimpleNamespace

        return SimpleNamespace(type="test", seq=1, session_id="s", time=0.0)


@pytest.fixture(autouse=True)
def _bound_publish_session() -> Iterator[None]:
    """Reasoner emit(prompt_assembler.assemble.*) 走 publish_via_session,
    无绑定 Session 时 fail-loud(ADR-0186);S1 鉴权需要授权目录的
    EventBus。绑测试 bus + 最小 fake Session 让 emit 通过
    (与 tests/plugins/events/publishers/conftest.py 同形)。
    """
    bus = build_test_bus()
    EventBus.set_default(bus)
    token = set_publish_session(_FakePublishSession())
    try:
        yield
    finally:
        reset_publish_session(token)
        EventBus.set_default(None)


def test_assembler_walks_template_section_refs() -> None:
    """End-to-end assembly uses the real provider + registry + section classes."""

    provider = _ProviderImpl(_templates=_builtin_templates())
    registry = _registry_with_builtins()
    assembler = SectionManifestPromptAssembler(
        registry=registry,
        template_provider=provider,
        strip_empty_fields=True,
    )

    state = _empty_state()
    prompt, _trace = assembler.render(
        template_id="react_prompt",
        role_profile=_profile("solo"),
        task=state.task,
        awareness=None,
        manifest=None,
        tools=[],
        activated_skills=(),
    )

    assert "ROLE: solo" in prompt
    assert "GOAL: goal of solo" in prompt
    assert "BACKSTORY: backstory of solo" in prompt
    assert "USER_TASK: probe" in prompt


def test_selector_routes_to_hierarchical_when_consult_duty_set() -> None:
    selector = TeamAwarenessTemplateSelector()
    state = AgentState(
        trace_id="t",
        task="probe",
        budget=Budget(),
        team_awareness=TeamAwareness(
            teammates=[],
            consult_duty=ConsultDuty(
                member_status=InMemoryMemberStatus(role_order=("x",)),
                max_attempts=2,
            ),
        ),
    )
    assert selector.select(state=state) == ("hierarchical_prompt", "consult_duty")


def test_selector_routes_to_routing_when_consult_duty_is_none() -> None:
    selector = TeamAwarenessTemplateSelector()
    state = _empty_state(team_awareness=TeamAwareness(teammates=[]))
    assert selector.select(state=state) == ("routing_prompt", "team_awareness_routing")


def test_routing_prompt_renders_member_reports_and_excludes_duplicates() -> None:
    """Cross-section state agreement: MEMBER_REPORTS owns the fact, CONTEXT is filtered."""

    provider = _ProviderImpl(_templates=_builtin_templates())
    registry = _registry_with_builtins()
    assembler = SectionManifestPromptAssembler(
        registry=registry,
        template_provider=provider,
        strip_empty_fields=True,
    )

    state = _empty_state(
        team_awareness=TeamAwareness(
            teammates=[_profile("Alice")],
            assigned_roles=["Alice"],
            results=[
                DelegationResult(
                    result_id="r1",
                    target_role="Alice",
                    subtask="tech risk",
                    output="compatibility is the core risk",
                    success=True,
                    error=None,
                    task_id=None,
                    step=0,
                    returned_at=None,
                )
            ],
        )
    )
    delegation_record = MemoryRecord(
        record_id="mem_1",
        content="compatibility is the core risk",
        memory_type=MemoryLayer.WORKING,
        importance=0.9,
        kind=MemoryRecordKind.DELEGATION_RESULT,
        metadata={"role": "Alice", "step": 0},
    )
    memory_manifest = ContextManifest(
        items=(
            ContextItem(
                kind="memory",
                payload=[delegation_record],
                provenance="memory.perceive",
            ),
        )
    )

    prompt, _trace = assembler.render(
        template_id="routing_prompt",
        role_profile=_profile("Lead"),
        task=state.task,
        awareness=state.team_awareness,
        manifest=memory_manifest,
        tools=[],
        activated_skills=(),
    )

    assert "MEMBER_REPORTS" in prompt
    assert "Alice | step 0" in prompt
    # CONTEXT excludes delegation records in free-routing mode.
    assert "Alice 已返回(step=0)" not in prompt


def _reasoner() -> PromptReasoner:
    return PromptReasoner(
        llm=_NoopLLM(),
        selector=TeamAwarenessTemplateSelector(),
        template_provider=_ProviderImpl(_templates=_builtin_templates()),
        section_registry=_registry_with_builtins(),
    )


class _NoopLLM:
    name = "noop"


def _clock_manifest() -> ContextManifest:
    return ContextManifest(
        items=(
            ContextItem(
                kind="clock",
                payload="2026-09-17 Thursday",
                provenance="clock_sensor",
            ),
        )
    )


@dataclass(frozen=True)
class _StubBrain:
    reasoner: Any
    role_profile: Any


@dataclass(frozen=True)
class _StubRuntime:
    state: AgentState
    brain: _StubBrain


def _drive_render(state: AgentState, template_id: str) -> Any:
    """Run the shipped ``think.reason.render`` node against a real reasoner."""

    from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnPlan
    from lca.contracts.protocols.declarative.declarative_1.node_executor import (
        NodeContext,
        NodeInput,
    )
    from lca.nodes.think.reason.render import ThinkReasonRenderExecutor

    reasoner = _reasoner()
    runtime = _StubRuntime(
        state=state,
        brain=_StubBrain(reasoner=reasoner, role_profile=_profile("solo")),
    )
    plan = ReasonerTurnPlan(
        state_id=state.trace_id,
        template_id=template_id,
        decision_path="profile_default",
        activated_skill_ids=(),
        tools_count=0,
        available_skills_count=0,
        sections_preview=(),
        variant_preview="react",
    )
    output = asyncio.run(
        ThinkReasonRenderExecutor().node_execute(
            NodeContext(runtime=runtime, budget={}, metadata={}),
            NodeInput(port_values={"turn_plan": plan}),
        )
    )
    return output.port_values["turn_render"]


def test_think_reason_render_puts_the_perceive_clock_in_the_system_prompt() -> None:
    """The clock the perceive hub produced must reach the model.

    ``run_e204465f48d6`` asked for today's news on 2026-09-17 and the model
    searched ``今日新闻 2025``: the manifest carried
    ``clock=2026-09-17 Thursday`` but the rendered system prompt had no
    ``CURRENT_DATE`` line, so the model fell back to its training-cutoff year.
    """

    state = _empty_state()
    state.perceive = PerceiveProjection(manifest=_clock_manifest(), digest="d", step=0)

    render = _drive_render(state, "react_prompt")

    assert "CURRENT_DATE: 2026-09-17 Thursday" in render.prompt
    assert "USER_TASK: probe" in render.prompt


def test_think_reason_render_reports_a_missing_clock_instead_of_dropping_the_line() -> None:
    """No clock item renders a visible placeholder, never a silently absent line."""

    render = _drive_render(_empty_state(), "react_prompt")

    assert "CURRENT_DATE: (未知当前时间)" in render.prompt


def test_think_reason_render_carries_the_manifest_to_the_model_visible_writer() -> None:
    """``context_manifest`` in the journal is sourced from ``turn_render.manifest``."""

    manifest = _clock_manifest()
    state = _empty_state()
    state.perceive = PerceiveProjection(manifest=manifest, digest="d", step=0)

    render = _drive_render(state, "react_prompt")

    assert render.manifest is manifest


def test_render_template_helper_strips_empty_fields() -> None:
    """`render_template` collapses ``LABEL: \\n`` lines so they don't waste tokens."""

    template = PromptTemplate(
        id="t",
        variant="react",
        sections=(
            SectionReference(name="role", kind="pure"),
            SectionReference(name="goal", kind="pure"),
        ),
    )
    registry = _registry_with_builtins()
    text = render_template(
        template=template,
        registry=registry,
        role_profile=RoleProfile(
            role="",
            goal="",
            backstory="",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        ),
        awareness=None,
        manifest=None,
        tools=[],
        activated_skills=(),
    )
    # Both sections render empty values for the empty profile; ``strip_empty_fields``
    # collapses the ``ROLE: \\nGOAL: \\n`` lines so the prompt stays terse.
    assert "ROLE:" not in text
    assert "GOAL:" not in text


@pytest.mark.parametrize("template_id", sorted(_builtin_templates()))
def test_every_builtin_template_anchors_the_model_to_today(template_id: str) -> None:
    """No template may ship without the date anchor.

    ``_builtin_section_refs`` slices one flat tuple by hand-maintained counts,
    so a template can lose ``current_date`` without any single section test
    noticing. A model with no date answers from its training cutoff.
    """

    assembler = SectionManifestPromptAssembler(
        registry=_registry_with_builtins(),
        template_provider=_ProviderImpl(_templates=_builtin_templates()),
        strip_empty_fields=True,
    )

    prompt, trace = assembler.render(
        template_id=template_id,
        role_profile=_profile("solo"),
        task="今天有什么新闻吗",
        awareness=None,
        manifest=_clock_manifest(),
        tools=[],
        activated_skills=(),
    )

    assert "CURRENT_DATE: 2026-09-17 Thursday" in prompt
    assert "current_date" in {section.name for section in trace.sections}
