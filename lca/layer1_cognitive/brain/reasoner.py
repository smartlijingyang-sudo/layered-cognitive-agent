"""PromptReasoner — call LLM to generate candidate thoughts.

solo / member / lead 共用同一个 Reasoner（ADR-0035）：状态携带
``TeamAwareness`` 时并入 awareness 变量并采用 awareness 默认模板，
否则走角色 react 模板。不按会话类型分支——awareness 通过纯函数
自行渲染提示词变量，Reasoner 只负责模板与 LLM 机制。
"""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.delegation import DelegationResult
from lca.contracts.enums import MemoryRecordKind
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols import LLMAdapter, Reasoner, Tool
from lca.contracts.role_team import RoleProfile
from lca.contracts.semantic_keys import META_ROLE, META_STEP
from lca.contracts.state import AgentState
from lca.contracts.team_awareness import TeamAwareness
from lca.contracts.telemetry import ATTR_PROMPT_TEMPLATE
from lca.layer0_infra.observability import annotate

_DEFAULT_TEMPLATE = "react_prompt"
_HIERARCHICAL_TEMPLATE = "hierarchical_prompt"
_ROUTING_TEMPLATE = "routing_prompt"
_EMPTY_TEAMMATES = "(无可用队友)"
_EMPTY_ASSIGNED = "(尚未委派)"
_EMPTY_CONTEXT = "(无历史上下文)"
_EMPTY_REPORTS = "(尚无成员回报)"
_EMPTY_NOTES = "(无)"
_KIND_EXCLUDE_NONE: frozenset[MemoryRecordKind] = frozenset()
_REPORT_EXCLUDED_KINDS: frozenset[MemoryRecordKind] = frozenset(
    {MemoryRecordKind.DELEGATION_RESULT}
)


def build_teammates_text(profiles: list[RoleProfile]) -> str:
    if not profiles:
        return _EMPTY_TEAMMATES
    return "\n".join(f"- role: {p.role} | goal: {p.goal}" for p in profiles)


def _format_record_line(record: MemoryRecord) -> str:
    layer = record.memory_type.value
    if record.kind == MemoryRecordKind.DELEGATION_RESULT:
        role = record.metadata.get(META_ROLE, "?")
        step = record.metadata.get(META_STEP, "?")
        return f"- [{layer}] {role} 已返回(step={step}): {record.content}"
    if record.kind == MemoryRecordKind.RESPONSE:
        step = record.metadata.get(META_STEP, "?")
        return f"- [{layer}] 我此前的回复(step={step}): {record.content}"
    return f"- [{layer}] {record.content}"


def _context_lines(
    state: AgentState, *, exclude_kinds: frozenset[MemoryRecordKind] = _KIND_EXCLUDE_NONE
) -> str:
    lines = [_format_record_line(r) for r in state.retrieved_context if r.kind not in exclude_kinds]
    return "\n".join(lines) or _EMPTY_CONTEXT


def build_member_reports_text(results: Sequence[DelegationResult]) -> str:
    """Render returned member reports as the lead's authoritative fact view."""
    if not results:
        return _EMPTY_REPORTS
    lines: list[str] = []
    for item in results:
        if item.success:
            outcome = f"已返回: {item.output or ''}"
        else:
            outcome = f"失败({item.error or '未知原因'})，可重新委派"
        lines.append(
            f"- {item.target_role} | step {item.step} | 子任务: {item.subtask} | {outcome}"
        )
    return "\n".join(lines)


def default_template_for(awareness: TeamAwareness) -> str:
    """Awareness 默认模板：有咨询义务走层级提示词，否则自由 routing。"""
    if awareness.consult_duty is not None:
        return _HIERARCHICAL_TEMPLATE
    return _ROUTING_TEMPLATE


def context_exclusions_for(awareness: TeamAwareness) -> frozenset[MemoryRecordKind]:
    """自由 routing 下回报记录（MEMBER_REPORTS）是委派事实的权威视图，
    从 CONTEXT 中剔除重复的委派记录；义务路径由状态板表达。"""
    if awareness.consult_duty is None:
        return _REPORT_EXCLUDED_KINDS
    return _KIND_EXCLUDE_NONE


def build_awareness_variables(awareness: TeamAwareness) -> dict[str, str]:
    """Awareness 自行渲染提示词变量——Reasoner 不窥探其内部形态。"""
    variables = {"teammates": build_teammates_text(awareness.teammates)}
    duty = awareness.consult_duty
    if duty is not None:
        variables["member_status_text"] = duty.member_status.as_prompt_text()
        return variables
    assigned = ", ".join(awareness.assigned_roles) if awareness.assigned_roles else _EMPTY_ASSIGNED
    variables["assigned_roles_text"] = assigned
    variables["notes"] = awareness.notes or _EMPTY_NOTES
    variables["member_reports_text"] = build_member_reports_text(awareness.results)
    return variables


def _role_prompt_vars(
    role_profile: RoleProfile,
    tools_desc: str,
    allowed_actions_desc: str,
    state: AgentState,
    context_lines: str,
) -> dict[str, str]:
    return {
        "role": role_profile.role,
        "goal": role_profile.goal,
        "backstory": role_profile.backstory,
        "tools": tools_desc,
        "task": state.task,
        "context": context_lines,
        "allowed_actions": allowed_actions_desc,
    }


def _with_subtasks(variables: dict[str, str], state: AgentState) -> dict[str, str]:
    subtasks = state.working_memory.get("subtasks")
    if not subtasks:
        return variables
    enriched = dict(variables)
    enriched["context"] = (
        enriched["context"] + "\n\nSubtasks:\n" + "\n".join(f"- {s}" for s in subtasks)
    )
    return enriched


async def _complete_candidates(
    llm: LLMAdapter,
    tools: list[Tool],
    templates: dict[str, str],
    template_name: str,
    variables: dict[str, str],
    n: int,
) -> list[str]:
    prompt = templates[template_name].format(**variables)
    annotate(**{ATTR_PROMPT_TEMPLATE: template_name})
    responses = [await llm.complete(prompt, tools=tools) for _ in range(max(1, n))]
    return [r.text for r in responses]


class PromptReasoner(Reasoner):
    """Default Reasoner: render prompt template and call the LLM.

    Team-shape agnostic by construction: the lead's team cognition arrives
    as ``AgentState.team_awareness`` and renders itself via
    ``build_awareness_variables`` / ``default_template_for`` — the reasoner
    never branches on mandate or session shape.
    """

    def __init__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        tools: Sequence[Tool] | None = None,
        templates: dict[str, str] | None = None,
        allowed_actions_desc: str = "",
    ) -> None:
        self.llm = llm
        self.role_profile = role_profile
        self.tools_desc = tools_desc
        self.tools: list[Tool] = list(tools) if tools else []
        self._templates: dict[str, str] = dict(templates or {})
        self.allowed_actions_desc = allowed_actions_desc

    def register_template(self, name: str, template: str) -> None:
        self._templates[name] = template

    async def generate_thoughts(self, state: AgentState, n: int = 1) -> list[str]:
        awareness = state.team_awareness
        exclusions = (
            context_exclusions_for(awareness) if awareness is not None else _KIND_EXCLUDE_NONE
        )
        variables = _role_prompt_vars(
            self.role_profile,
            self.tools_desc,
            self.allowed_actions_desc,
            state,
            _context_lines(state, exclude_kinds=exclusions),
        )
        template_name = state.active_template or _DEFAULT_TEMPLATE
        if awareness is not None:
            variables.update(build_awareness_variables(awareness))
            template_name = state.active_template or default_template_for(awareness)
        variables = _with_subtasks(variables, state)
        return await _complete_candidates(
            self.llm, self.tools, self._templates, template_name, variables, n
        )
