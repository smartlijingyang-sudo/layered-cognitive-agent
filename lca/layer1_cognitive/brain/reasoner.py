"""PromptReasoner — call LLM to generate candidate thoughts.

solo / member / lead 共用同一个 Reasoner（ADR-0035）：状态携带
``TeamAwareness`` 时并入 awareness 变量并采用 awareness 默认模板，
否则走角色 react 模板。不按会话类型分支——awareness 通过纯函数
自行渲染提示词变量，Reasoner 只负责模板与 LLM 机制。

LLM 调用语义对齐 LobeHub ``call_llm``（``brain/llm_turn``）：每 step 一次
LLM，text-only 即 respond，禁止 forced ``tool_choice=required``。
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from lca.contracts.atoms.enums import MemoryRecordKind
from lca.contracts.atoms.telemetry import ATTR_PROMPT_TEMPLATE
from lca.contracts.models.core.conversation import (
    PRIOR_CONVERSATION_WM_KEY,
    ConversationTurn,
)
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.delegation import DelegationResult
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.team_awareness import TeamAwareness
from lca.contracts.protocols import LLMAdapter, Reasoner, Tool
from lca.layer0_infra.observability import annotate
from lca.layer0_infra.search.router import search_routing_hint
from lca.layer0_infra.search.service import any_search_provider_available
from lca.layer1_cognitive.brain.conversation_prompt import format_prior_conversation
from lca.layer1_cognitive.brain.llm_turn import execute_llm_turn

_DEFAULT_TEMPLATE = "react_prompt"
_HIERARCHICAL_TEMPLATE = "hierarchical_prompt"
_ROUTING_TEMPLATE = "routing_prompt"
_EMPTY_TEAMMATES = "(无可用队友)"
_EMPTY_ASSIGNED = "(尚未委派)"
_EMPTY_CONTEXT = "(无历史上下文)"
_EMPTY_REPORTS = "(尚无成员回报)"
_KIND_EXCLUDE_NONE: frozenset[MemoryRecordKind] = frozenset()
_REPORT_EXCLUDED_KINDS: frozenset[MemoryRecordKind] = frozenset(
    {MemoryRecordKind.DELEGATION_RESULT}
)

_EMPTY_FIELD_RE = re.compile(r"^[A-Z_]+: \s*$", re.MULTILINE)
"""匹配 prompt 模板渲染后内联字段值为空的行（如 'GOAL: \\n'），solo 裸模型场景需要剥离。

只匹配 ``LABEL: ``（冒号后有空格但无内容）——区分于 ``LABEL:\\n{content}``
块标签（如 TEAMMATES:/MEMBER_STATUS: 后接多行内容，不应剥离）。
"""


def _strip_empty_prompt_fields(prompt: str) -> str:
    """剥离 prompt 中值为空的字段行（ADR-0052 solo 裸模型）。

    模板 ``ROLE: {role}\\nGOAL: {goal}\\nBACKSTORY: {backstory}`` 在 solo 场景
    goal/backstory 为空时会渲染成 ``GOAL: \\nBACKSTORY: \\n``，浪费 token 且
    干扰模型。此函数把这类空行整行移除。
    """
    return _EMPTY_FIELD_RE.sub("", prompt).strip("\n")


def build_teammates_text(profiles: list[RoleProfile]) -> str:
    if not profiles:
        return _EMPTY_TEAMMATES
    return "\n".join(f"- role: {p.role} | goal: {p.goal}" for p in profiles)


def _format_record_line(record: MemoryRecord) -> str:
    layer = record.memory_type.value
    if record.kind == MemoryRecordKind.DELEGATION_RESULT:
        role = record.metadata.get("role", "?")
        step = record.metadata.get("step", "?")
        return f"- [{layer}] {role} 已返回(step={step}): {record.content}"
    if record.kind == MemoryRecordKind.RESPONSE:
        step = record.metadata.get("step", "?")
        return f"- [{layer}] 我此前的回复(step={step}): {record.content}"
    return f"- [{layer}] {record.content}"


def _trace_lines(state: AgentState) -> list[str]:
    """Render execution trace from state.history — every step's action→outcome.

    This is the ReAct observation channel: the LLM must see what happened at
    each step (tool called, success/failure, error details) to reason about
    the next action.  Memory records are curated insights; the trace is the
    raw execution record.  Both are needed; neither substitutes the other.
    """
    lines: list[str] = []
    for turn in state.history:
        decision = turn.decision
        observation = turn.observation
        step = len(lines)
        action = decision.action_type
        if action == "use_tool" and decision.tool_calls:
            tool_name = decision.tool_calls[0].tool_name
            if observation.success:
                detail = _truncate(f"success, result={observation.payload}", 200)
            else:
                detail = f"failed: {observation.error or 'unknown error'}"
            lines.append(f"- step{step}: {action}({tool_name}) → {detail}")
        elif action == "respond":
            snippet = _truncate(decision.response_text or "", 100)
            lines.append(f"- step{step}: respond → {snippet}")
        elif action == "delegate" and decision.delegations:
            target = decision.delegations[0].target_role or "?"
            if observation.success:
                detail = _truncate(f"success, result={observation.payload}", 200)
            else:
                detail = f"failed: {observation.error or 'unknown error'}"
            lines.append(f"- step{step}: delegate({target}) → {detail}")
        else:
            status = "success" if observation.success else "failed"
            lines.append(f"- step{step}: {action} → {status}")
    return lines


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _context_lines(
    state: AgentState, *, exclude_kinds: frozenset[MemoryRecordKind] = _KIND_EXCLUDE_NONE
) -> str:
    # Execution trace: raw action→outcome for every step (ReAct observation channel)
    trace = _trace_lines(state)
    # Memory records: curated insights from working/episodic/semantic/procedural
    mem_lines = [
        _format_record_line(r) for r in state.retrieved_context if r.kind not in exclude_kinds
    ]
    parts = trace + mem_lines
    return "\n".join(parts) or _EMPTY_CONTEXT


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
    from lca.contracts.models.team.consultation import build_evidence_pack_text

    variables = {"teammates": build_teammates_text(awareness.teammates)}
    duty = awareness.consult_duty
    if duty is not None:
        variables["member_status_text"] = duty.member_status.as_prompt_text()
        variables["evidence_pack_text"] = build_evidence_pack_text(duty.outcomes)
        return variables
    assigned = ", ".join(awareness.assigned_roles) if awareness.assigned_roles else _EMPTY_ASSIGNED
    variables["assigned_roles_text"] = assigned
    variables["member_reports_text"] = build_member_reports_text(awareness.results)
    variables["evidence_pack_text"] = ""
    return variables


def _format_activated_skills(state: AgentState) -> str:
    if not state.activated_skills:
        return "（无）"
    return "\n".join(
        f"- {s.name} ({s.skill_id}, step {s.activated_at_step} 激活)"
        for s in state.activated_skills
    )


def _prior_conversation_text(state: AgentState) -> str:
    raw = state.working_memory.get(PRIOR_CONVERSATION_WM_KEY)
    if not isinstance(raw, list) or not raw:
        return format_prior_conversation(())
    turns: list[ConversationTurn] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role and content:
            turns.append(ConversationTurn(role=role, content=content))
    return format_prior_conversation(tuple(turns))


def _role_prompt_vars(
    role_profile: RoleProfile,
    tools_desc: str,
    state: AgentState,
    context_lines: str,
    *,
    available_skills: str = "",
) -> dict[str, str]:
    return {
        "role": role_profile.role,
        "goal": role_profile.goal,
        "backstory": role_profile.backstory,
        "tools": tools_desc,
        "task": state.task,
        "prior_conversation": _prior_conversation_text(state),
        "context": context_lines,
        "available_skills": available_skills or "（无技能库）",
        "activated_skills": _format_activated_skills(state),
        "search_routing": search_routing_hint(tavily_available=any_search_provider_available()),
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


def _with_loop_warning(variables: dict[str, str], state: AgentState) -> dict[str, str]:
    """Inject loop-intervention warning into the prompt context if present.

    The runtime loop injects this into working_memory when it detects
    consecutive same-tool calls (Phase 3.6).  The model sees it on the
    next think phase and can change strategy.
    """
    warning = state.working_memory.get("loop_warning")
    if not warning:
        return variables
    enriched = dict(variables)
    enriched["context"] = enriched["context"] + f"\n\n{warning}"
    return enriched


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
        available_skills: str = "",
    ) -> None:
        self.llm = llm
        self.role_profile = role_profile
        self.tools_desc = tools_desc
        self.tools: list[Tool] = list(tools) if tools else []
        self._templates: dict[str, str] = dict(templates or {})
        self.available_skills = available_skills

    def register_template(self, name: str, template: str) -> None:
        self._templates[name] = template

    async def generate_thoughts(self, state: AgentState) -> LLMResponse:
        awareness = state.team_awareness
        exclusions = (
            context_exclusions_for(awareness) if awareness is not None else _KIND_EXCLUDE_NONE
        )
        variables = _role_prompt_vars(
            self.role_profile,
            self.tools_desc,
            state,
            _context_lines(state, exclude_kinds=exclusions),
            available_skills=self.available_skills,
        )
        template_name = state.active_template or _DEFAULT_TEMPLATE
        if awareness is not None:
            variables.update(build_awareness_variables(awareness))
            template_name = state.active_template or default_template_for(awareness)
        variables = _with_subtasks(variables, state)
        variables = _with_loop_warning(variables, state)
        prompt = self._templates[template_name].format(**variables)
        prompt = _strip_empty_prompt_fields(prompt)
        annotate(**{ATTR_PROMPT_TEMPLATE: template_name})
        task = variables.get("task", "")
        return await execute_llm_turn(
            self.llm,
            self.tools,
            prompt,
            step=state.step,
            state=state,
            task=task,
        )
