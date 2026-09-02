"""Prompt sections — one Cordis plugin that registers 17 typed sections.

The brain prompt is composed entirely from typed section providers. Each
section is a small class implementing ``PureSection`` or ``StatefulSection``;
the assembler walks a ``PromptTemplate``'s ``SectionReference`` list and
resolves each section through the ``PromptSectionRegistry``.

Sections live in this single Cordis plugin (instead of one file per
section) because the design rule is **one plugin id per profile-managed
unit of work**, not one plugin id per data class. Each section is a
declarative instance, the plugin's job is to register them all. Profile
YAML can still toggle per-section Config keys to customise the text.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from lca.cognition.brain.sandbox_prompt import build_cloud_sandbox_prompt
from lca.cognition.brain.sections.types import (
    block,
    clock_from_state,
    join_lines,
    label_line,
    render_activated_skills,
    render_artifacts_block,
    render_assigned_roles,
    render_context_lines,
    render_member_reports,
    render_prior_conversation_from_state,
    render_subtasks_block,
    render_teammates,
)
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import PROMPT_SECTION_REGISTRY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.cognition.prompt_assembly import (
    SectionOutput,
)
from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.team_awareness import TeamAwareness
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.runtime.infra import Tool
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# ── Per-section Pydantic Config ────────────────────────────────────


class _EmptyConfig(BaseModel):
    """Default empty Config — sections with no per-instance knobs."""

    model_config = ConfigDict(extra="forbid")


class _RoleConfig(_EmptyConfig):
    """Role section has no knobs; kept as a class to anchor plugin typing."""


class _TextConfig(_EmptyConfig):
    """Static instruction blocks read their text from Config.text."""

    text: str


class _ToolsConfig(_EmptyConfig):
    """Tools section has no knobs — catalog content is injected at render time."""


# ── PureSection implementations ───────────────────────────────────


class RoleSection:
    name: ClassVar[str] = "role"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        return SectionOutput(text=label_line("ROLE", role_profile.role))


class GoalSection:
    name: ClassVar[str] = "goal"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        return SectionOutput(text=label_line("GOAL", role_profile.goal))


class BackstorySection:
    name: ClassVar[str] = "backstory"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        return SectionOutput(text=label_line("BACKSTORY", role_profile.backstory))


@dataclass
class ToolsSection:
    """Renders the model's <tools> block plus the cloud-sandbox <tool> entries.

    Pulled together so the assembler only has one slot to fill and so
    the cloud_sandbox block stays embedded in its natural wrapper
    instead of being emitted as a separate label-less chunk.
    """

    catalog_tools_xml_provider: Callable[[], str]
    name: ClassVar[str] = "tools"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        catalog_xml = self.catalog_tools_xml_provider() or ""
        cloud_sandbox = build_cloud_sandbox_prompt(list(tools)) if tools else ""
        body = "\n".join(part for part in (catalog_xml, cloud_sandbox) if part)
        return SectionOutput(text=block("tools", body))


@dataclass
class AvailableSkillsSection:
    catalog_skills_provider: Callable[[], str]
    name: ClassVar[str] = "available_skills"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        return SectionOutput(text=block("available_skills", self.catalog_skills_provider()))


@dataclass
class StaticTextSection:
    """A pure section whose text is provided via Config.text."""

    name: ClassVar[str]  # set per subclass
    text: str

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        return SectionOutput(text=self.text)


class ReactWorkflowSection(StaticTextSection):
    name = "react_workflow"


class ReactToolUsageSection(StaticTextSection):
    name = "react_tool_usage_guidelines"


class RoutingInstructionsSection(StaticTextSection):
    name = "routing_instructions"


class HierarchicalInstructionsSection(StaticTextSection):
    name = "hierarchical_instructions"


# ── StatefulSection implementations ────────────────────────────────


class CurrentDateSection:
    name: ClassVar[str] = "current_date"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        # Prefer the manifest's typed clock item over a parameter.
        clock = clock_from_state(state)
        text = clock.text if clock else "(未知当前时间)"
        return SectionOutput(text=label_line("CURRENT_DATE", text))


class TaskSection:
    name: ClassVar[str] = "task"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        return SectionOutput(text=label_line("USER_TASK", state.task or ""))


class PriorConversationSection:
    name: ClassVar[str] = "prior_conversation"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        text = render_prior_conversation_from_state(state)
        return SectionOutput(text=label_line("PRIOR_CONVERSATION", text))


class ActivatedSkillsSection:
    name: ClassVar[str] = "activated_skills"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        return SectionOutput(text=block("activated_skills", render_activated_skills(state)))


class ContextSection:
    name: ClassVar[str] = "context"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        from lca.cognition.brain.sections.types import context_exclusions_for

        exclude = context_exclusions_for(awareness)
        base = render_context_lines(state, exclude_kinds=exclude)
        subtasks_block = render_subtasks_block(state)
        artifacts_block = render_artifacts_block(state)
        body = join_lines([base, subtasks_block, artifacts_block])
        return SectionOutput(text=label_line("CONTEXT", body))


class TeammatesSection:
    name: ClassVar[str] = "teammates"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        profiles = awareness.teammates if awareness is not None else ()
        return SectionOutput(text=label_line("TEAMMATES", render_teammates(profiles)))


class AssignedRolesSection:
    name: ClassVar[str] = "assigned_roles_text"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        roles = awareness.assigned_roles if awareness is not None else ()
        return SectionOutput(text=label_line("ALREADY_ASSIGNED", render_assigned_roles(roles)))


class MemberReportsSection:
    name: ClassVar[str] = "member_reports_text"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        results = awareness.results if awareness is not None else ()
        return SectionOutput(
            text=label_line(
                "MEMBER_REPORTS（你已发起委派的返回，确定性事实，不是历史记录）",
                render_member_reports(results),
            )
        )


class MemberStatusSection:
    name: ClassVar[str] = "member_status_text"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        if awareness is None or awareness.consult_duty is None:
            return SectionOutput(text="(无状态板)")
        return SectionOutput(text=label_line("MEMBER_STATUS", awareness.consult_duty.member_status.as_prompt_text()))


class EvidencePackSection:
    name: ClassVar[str] = "evidence_pack_text"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        from lca.contracts.models.team.consultation import build_evidence_pack_text

        outcomes = awareness.consult_duty.outcomes if awareness and awareness.consult_duty else ()
        text = build_evidence_pack_text(outcomes)
        return SectionOutput(
            text=label_line(
                "EVIDENCE_PACK（成员已返回的可综合证据；部分证据也算有效视角）",
                text,
            )
        )


# ── Profile-driven text blocks (must live here, not in modules/types) ─────
# The static instruction blocks are content policy owned by the profile,
# but the section surface is owned by the L1 primitive. Profiles can override
# these via plugin config when more than the built-in is needed.

_REACT_WORKFLOW_TEXT = """<workflow>
1. Understand the user's request.
2. Select the appropriate tool(s) for the task.
3. Execute operations.
4. Present results clearly.
5. Export files by default when the user asks to create/generate/save something.
</workflow>"""

_REACT_TOOL_USAGE_TEXT = """<tool_usage_guidelines>
- Tools in <tools> are called via function calling (native tool_calls)
- Skills in <available_skills> require activate_skill first; <activated_skills> are already active
- Each step: one LLM call only — text and tool_calls belong to the same completion
- When tools are needed: use function calling (native tool_calls), do not output text then call tools separately
- When no tools are needed: reply with text directly (pure text response ends the step)
- Real-time news/search: follow search routing above, prefer web_search
- Reply in standard Markdown format
</tool_usage_guidelines>"""

_ROUTING_INSTRUCTIONS_TEXT = """你是团队主导者（lead，自由路由模式）。

## 工作规则
1. 根据任务动态决定是否需要队友、需要谁、如何表述子任务——不必咨询全部角色。
2. MEMBER_REPORTS 中列出的每一条，就是对应委派**已经返回**的结果——它们是你的事实来源，
   不是需要重新触发的历史记录。信息足够时直接文字回复综合结论；不要为了"走完流程"而委派。
3. 严禁重复委派 MEMBER_REPORTS 中已有返回的相同（角色, 子任务）。只有当某次委派标记为失败、
   或你确实需要同一角色补充新内容时，才可再次委派该角色，且必须更换子任务表述并说明原因。
4. 自己动手时：<tools> 中的工具通过 function calling 调用；<activated_skills> 已激活可直接执行；
   <available_skills> 需先 activate_skill 加载指南。

## 委派
需要队友协助时，使用 delegate 工具（如果有）或通过 function calling 调用委派功能。
可以一次委派多个角色（并行），也可以单目标委派。

## 输出规则
- 需要调用工具时，使用 function calling（原生 tool_calls）
- 不需要工具时，直接用文字回复用户
- 回复使用标准 Markdown 格式"""

_HIERARCHICAL_INSTRUCTIONS_TEXT = """你是团队主导者（lead）。

## 工作规则
1. 每一轮先审视 EVIDENCE_PACK 与 CONTEXT 中已有的委派结果，判断哪些队友尚未提供**可用**输入。
2. 若 MEMBER_STATUS 仍显示待咨询角色，且框架未自动委派，可 delegate 给尚未发言的队友。
3. 当所有角色已终态（完整证据 / 部分证据 / 失败）后，直接文字回复综合；**必须优先吸收 EVIDENCE_PACK**，不得假装未见。
4. 禁止把同一个子任务反复委派给同一角色——每个角色最多有效咨询一次；部分证据也算已覆盖该视角。
5. 若部分角色失败且无证据，在回复中明确标注缺失视角并给出 lead 兜底，勿空转重试。
6. 自己动手时：<tools> 中的工具通过 function calling 调用；<activated_skills> 已激活可直接执行；
   <available_skills> 需先 activate_skill 加载指南。

## 委派
需要队友协助时，使用 delegate 工具（如果有）或通过 function calling 调用委派功能。
委派时说明 target_role 和 subtask。

## 输出规则
- 需要调用工具时，使用 function calling（原生 tool_calls）
- 不需要工具时，直接用文字回复用户
- 回复使用标准 Markdown 格式"""


# ── Built-in section factories (closed set, 17 sections) ──────────


def build_role_section(config: BaseModel) -> RoleSection:
    del config
    return RoleSection()


def build_goal_section(config: BaseModel) -> GoalSection:
    del config
    return GoalSection()


def build_backstory_section(config: BaseModel) -> BackstorySection:
    del config
    return BackstorySection()


def build_tools_section(
    config: BaseModel, *, catalog: Callable[[], str]
) -> ToolsSection:
    del config
    return ToolsSection(catalog_tools_xml_provider=catalog)


def build_available_skills_section(
    config: BaseModel, *, catalog: Callable[[], str]
) -> AvailableSkillsSection:
    del config
    return AvailableSkillsSection(catalog_skills_provider=catalog)


def build_static_text(config: BaseModel, name: str, default_text: str) -> StaticTextSection:
    """Bind a config text value to a StaticTextSection instance."""

    text = getattr(config, "text", None) or default_text
    section = StaticTextSection(text=text)
    section.name = name
    return section


def build_react_workflow(config: BaseModel) -> StaticTextSection:
    return build_static_text(config, "react_workflow", _REACT_WORKFLOW_TEXT)


def build_react_tool_usage(config: BaseModel) -> StaticTextSection:
    return build_static_text(config, "react_tool_usage_guidelines", _REACT_TOOL_USAGE_TEXT)


def build_routing_instructions(config: BaseModel) -> StaticTextSection:
    return build_static_text(config, "routing_instructions", _ROUTING_INSTRUCTIONS_TEXT)


def build_hierarchical_instructions(config: BaseModel) -> StaticTextSection:
    return build_static_text(config, "hierarchical_instructions", _HIERARCHICAL_INSTRUCTIONS_TEXT)


# Stateful sections built from their config (none have knobs but kept
# for symmetry with the pure section factories).

def build_current_date(config: BaseModel) -> CurrentDateSection:
    del config
    return CurrentDateSection()


def build_task(config: BaseModel) -> TaskSection:
    del config
    return TaskSection()


def build_prior_conversation(config: BaseModel) -> PriorConversationSection:
    del config
    return PriorConversationSection()


def build_activated_skills(config: BaseModel) -> ActivatedSkillsSection:
    del config
    return ActivatedSkillsSection()


def build_context(config: BaseModel) -> ContextSection:
    del config
    return ContextSection()


def build_teammates(config: BaseModel) -> TeammatesSection:
    del config
    return TeammatesSection()


def build_assigned_roles(config: BaseModel) -> AssignedRolesSection:
    del config
    return AssignedRolesSection()


def build_member_reports(config: BaseModel) -> MemberReportsSection:
    del config
    return MemberReportsSection()


def build_member_status(config: BaseModel) -> MemberStatusSection:
    del config
    return MemberStatusSection()


def build_evidence_pack(config: BaseModel) -> EvidencePackSection:
    del config
    return EvidencePackSection()


# ── Config schema ────────────────────────────────────────────────


class Config(BaseModel):
    """Profile-driven per-section overrides.

    The default block texts are baked in. Profiles can override any
    instruction block via ``instruction_overrides: {name: text}`` —
    the section plugin then uses the overridden text verbatim.
    """

    model_config = ConfigDict(extra="forbid")
    instruction_overrides: dict[str, str] = {}


# ── Plugin wiring ────────────────────────────────────────────────


@plugin(
    id="lca-brain-prompt-sections",
    Config=Config,
    provides=[],
    requires=[PROMPT_SECTION_REGISTRY.key],
    layer="L1",
    effects="none",
    description="Provide the 17 typed prompt sections (pure + stateful).",
    test_suite="tests/architecture/test_prompt_section_registry.py",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-brain-prompt-sections.checked",
                "lca-brain-prompt-sections.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register every section in the closed 17-section set.

    The assembler resolves ``tools`` / ``available_skills`` through the
    active ``BrainPromptCatalog`` at render time, so the section module
    takes a ``catalog_provider`` callable bound at registration time
    (typically a closure over ``ctx.require(BRAIN_PROMPT_CATALOG_FACTORY.key)``).
    """

    registry = ctx.require(PROMPT_SECTION_REGISTRY.key)

    # Apply per-section overrides to the static instruction blocks.
    overrides = dict(config.instruction_overrides)
    for name, _default in (
        ("react_workflow", _REACT_WORKFLOW_TEXT),
        ("react_tool_usage_guidelines", _REACT_TOOL_USAGE_TEXT),
        ("routing_instructions", _ROUTING_INSTRUCTIONS_TEXT),
        ("hierarchical_instructions", _HIERARCHICAL_INSTRUCTIONS_TEXT),
    ):
        if name in overrides:
            globals()[f"_INSTRUCTION_OVERRIDE_{name.upper()}"] = overrides[name]

    # Pull catalog providers lazily so the section plugin does not
    # require the catalog at setup time — composition root order is
    # independent of which section plugin loads first.
    from lca.contracts.capabilities import BRAIN_PROMPT_CATALOG_FACTORY
    from lca.contracts.protocols.think.cognition import BrainPromptCatalogFactory

    try:
        catalog_factory = ctx.require(BRAIN_PROMPT_CATALOG_FACTORY.key)
    except Exception:
        catalog_factory = None

    def _catalog_render(render_method: str) -> Callable[[], str]:
        if catalog_factory is None or not isinstance(
            catalog_factory, BrainPromptCatalogFactory
        ):
            return lambda: ""

        sentinel = object()

        def _render() -> str:
            # Use an empty skill store + empty tool set as a stable
            # fallback when the catalog has not been specialised yet.
            try:

                class _EmptyStore:
                    def list_installed(self) -> tuple[object, ...]:
                        return ()

                catalog = catalog_factory.create(
                    skill_store=_EmptyStore(),  # type: ignore[arg-type]
                    tools=(),
                )
            except Exception:
                return ""
            method = getattr(catalog, render_method, sentinel)
            if method is sentinel:
                return ""
            try:
                return str(method())
            except Exception:
                return ""

        return _render

    # Pure sections
    pure_sections: list[tuple[str, object, str]] = [
        ("role", build_role_section(Config()), "static"),
        ("goal", build_goal_section(Config()), "static"),
        ("backstory", build_backstory_section(Config()), "static"),
        (
            "tools",
            build_tools_section(_ToolsConfig(), catalog=_catalog_render("render_tools_xml")),
            "catalog_xml",
        ),
        (
            "available_skills",
            build_available_skills_section(
                _ToolsConfig(), catalog=_catalog_render("render_brain_skills")
            ),
            "catalog_skills",
        ),
        ("react_workflow", build_react_workflow(Config()), "static"),
        ("react_tool_usage_guidelines", build_react_tool_usage(Config()), "static"),
        ("routing_instructions", build_routing_instructions(Config()), "static"),
        ("hierarchical_instructions", build_hierarchical_instructions(Config()), "static"),
    ]
    for name, section, _kind in pure_sections:
        registry.register(section, kind="pure", name=name)

    # Stateful sections
    stateful_sections: list[tuple[str, object]] = [
        ("current_date", build_current_date(Config())),
        ("task", build_task(Config())),
        ("prior_conversation", build_prior_conversation(Config())),
        ("activated_skills", build_activated_skills(Config())),
        ("context", build_context(Config())),
        ("teammates", build_teammates(Config())),
        ("assigned_roles_text", build_assigned_roles(Config())),
        ("member_reports_text", build_member_reports(Config())),
        ("member_status_text", build_member_status(Config())),
        ("evidence_pack_text", build_evidence_pack(Config())),
    ]
    for name, section in stateful_sections:
        registry.register(section, kind="stateful", name=name)


__all__ = [
    "ActivatedSkillsSection",
    "AssignedRolesSection",
    "AvailableSkillsSection",
    "BackstorySection",
    "Config",
    "ContextSection",
    "CurrentDateSection",
    "EvidencePackSection",
    "GoalSection",
    "HierarchicalInstructionsSection",
    "MemberReportsSection",
    "MemberStatusSection",
    "PriorConversationSection",
    "ReactToolUsageSection",
    "ReactWorkflowSection",
    "RoleSection",
    "RoutingInstructionsSection",
    "StaticTextSection",
    "TaskSection",
    "TeammatesSection",
    "ToolsSection",
    "setup",
]
