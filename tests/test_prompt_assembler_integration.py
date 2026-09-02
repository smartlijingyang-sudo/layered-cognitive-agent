"""PromptAssembler integration — production wiring with real registry + provider.

This test deliberately constructs ``_RegistryImpl``, ``_ProviderImpl``, the
section classes from ``lca.plugins.prompts.sections``, and
``SectionManifestPromptAssembler`` directly. No test-only helpers that
mock production wiring.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from lca.cognition.brain.reasoner import PromptReasoner
from lca.cognition.brain.sections.assembler import (
    SectionManifestPromptAssembler,
    render_template,
)
from lca.cognition.member_status import InMemoryMemberStatus
from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplate,
    SectionReference,
)
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.delegation import DelegationResult
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.team_awareness import ConsultDuty, TeamAwareness
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
    PriorConversationSection,
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
        ToolsSection(catalog_tools_xml_provider=lambda: "<tool name=\"x\">x</tool>"),
        kind="pure",
        name="tools",
    )
    registry.register(
        AvailableSkillsSection(catalog_skills_provider=lambda: "（无技能库）"),
        kind="pure",
        name="available_skills",
    )
    registry.register(ReactWorkflowSection(text="<workflow/>"), kind="pure", name="react_workflow")
    registry.register(ReactToolUsageSection(text="<usage/>"), kind="pure", name="react_tool_usage_guidelines")
    registry.register(RoutingInstructionsSection(text="routing-rules"), kind="pure", name="routing_instructions")
    registry.register(HierarchicalInstructionsSection(text="hier-rules"), kind="pure", name="hierarchical_instructions")
    # Stateful sections
    registry.register(CurrentDateSection(), kind="stateful", name="current_date")
    registry.register(TaskSection(), kind="stateful", name="task")
    registry.register(PriorConversationSection(), kind="stateful", name="prior_conversation")
    registry.register(ActivatedSkillsSection(), kind="stateful", name="activated_skills")
    registry.register(ContextSection(), kind="stateful", name="context")
    registry.register(TeammatesSection(), kind="stateful", name="teammates")
    registry.register(AssignedRolesSection(), kind="stateful", name="assigned_roles_text")
    registry.register(MemberReportsSection(), kind="stateful", name="member_reports_text")
    registry.register(MemberStatusSection(), kind="stateful", name="member_status_text")
    registry.register(EvidencePackSection(), kind="stateful", name="evidence_pack_text")
    return registry


# ── tests ──────────────────────────────────────────────────────────


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
    prompt = assembler.render(
        template_id="react_prompt",
        role_profile=_profile("solo"),
        state=state,
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
    assert selector.select(state=state) == "hierarchical_prompt"


def test_selector_routes_to_routing_when_consult_duty_is_none() -> None:
    selector = TeamAwarenessTemplateSelector()
    state = _empty_state(team_awareness=TeamAwareness(teammates=[]))
    assert selector.select(state=state) == "routing_prompt"


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
    state.retrieved_context = [
        MemoryRecord(
            record_id="mem_1",
            content="compatibility is the core risk",
            memory_type=MemoryLayer.WORKING,
            importance=0.9,
            kind=MemoryRecordKind.DELEGATION_RESULT,
            metadata={"role": "Alice", "step": 0},
        )
    ]

    prompt = assembler.render(
        template_id="routing_prompt",
        role_profile=_profile("Lead"),
        state=state,
        awareness=state.team_awareness,
        manifest=None,
        tools=[],
        activated_skills=(),
    )

    assert "MEMBER_REPORTS" in prompt
    assert "Alice | step 0" in prompt
    # CONTEXT excludes delegation records in free-routing mode.
    assert "Alice 已返回(step=0)" not in prompt


def test_reasoner_uses_assembler_and_selector_when_wired() -> None:
    """Reasoner defers rendering to the assembler; the LLM stub captures the prompt."""

    captured: dict[str, str] = {}

    class _CaptureLLM:
        name = "capture"

        async def complete(self, prompt: str, **kwargs: object) -> str:
            captured["complete"] = prompt
            return '{"action_type": "respond", "response_text": "ok"}'

        async def stream(self, prompt: str, **kwargs: object):
            captured["stream"] = prompt
            from lca.contracts.atoms.enums import LLMStreamEventType
            from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent

            text = '{"action_type": "respond", "response_text": "ok"}'
            captured["complete"] = text
            response = LLMResponse(text=text)
            yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
            yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)

    provider = _ProviderImpl(_templates=_builtin_templates())
    registry = _registry_with_builtins()
    assembler = SectionManifestPromptAssembler(
        registry=registry, template_provider=provider, strip_empty_fields=True
    )
    selector = TeamAwarenessTemplateSelector()
    llm = _CaptureLLM()
    reasoner = PromptReasoner(
        llm=llm,
        role_profile=_profile("solo"),
        tools_desc="(none)",
        assembler=assembler,
        selector=selector,
        tools=[],
    )

    asyncio.run(reasoner.generate_thoughts(_empty_state()))

    prompt = captured["stream"]
    assert "ROLE: solo" in prompt
    assert "USER_TASK: probe" in prompt


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
        state=_empty_state(),
        awareness=None,
        manifest=None,
        tools=[],
        activated_skills=(),
    )
    # Both sections render empty values for the empty profile; ``strip_empty_fields``
    # collapses the ``ROLE: \\nGOAL: \\n`` lines so the prompt stays terse.
    assert "ROLE:" not in text
    assert "GOAL:" not in text
