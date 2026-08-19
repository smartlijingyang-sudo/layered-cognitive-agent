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

from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.atoms.telemetry import ATTR_PROMPT_TEMPLATE
from lca.contracts.models.core.conversation import (
    PRIOR_CONVERSATION_WM_KEY,
    ConversationTurn,
)
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.delegation import DelegationResult
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.team_awareness import TeamAwareness
from lca.contracts.protocols import LLMAdapter, Reasoner, Tool
from lca.layer0_infra.observability import annotate
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
# Prompt CONTEXT is curated memory only. Tool I/O is provider history.
_PROMPT_WORKING_KINDS: frozenset[MemoryRecordKind] = frozenset(
    {MemoryRecordKind.DELEGATION_RESULT, MemoryRecordKind.RESPONSE}
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


def _is_prompt_context_record(record: MemoryRecord) -> bool:
    """LobeHub: tool I/O is ``role=tool``. CONTEXT is insights, not a second wire."""
    if record.kind == MemoryRecordKind.TOOL_RESULT:
        return False
    if record.memory_type in {
        MemoryLayer.SEMANTIC,
        MemoryLayer.PROCEDURAL,
        MemoryLayer.EPISODIC,
    }:
        return True
    return record.kind in _PROMPT_WORKING_KINDS


def _context_lines(
    state: AgentState, *, exclude_kinds: frozenset[MemoryRecordKind] = _KIND_EXCLUDE_NONE
) -> str:
    mem_lines = [
        _format_record_line(record)
        for record in state.retrieved_context
        if isinstance(record, MemoryRecord)
        and record.kind not in exclude_kinds
        and _is_prompt_context_record(record)
    ]
    return "\n".join(mem_lines) or _EMPTY_CONTEXT


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


def _cloud_sandbox_block(tools: Sequence[Tool]) -> str:
    if not tools:
        return ""
    from lca.layer1_cognitive.brain.sandbox_prompt import build_cloud_sandbox_prompt

    return build_cloud_sandbox_prompt(tools)


def _role_prompt_vars(
    role_profile: RoleProfile,
    tools_desc: str,
    state: AgentState,
    context_lines: str,
    *,
    tools: Sequence[Tool] | None = None,
    available_skills: str = "",
    manifest: ContextManifest | None = None,
) -> dict[str, str]:
    """Render the prompt's role-keyed variables.

    The ``current_date`` field is sourced from the manifest's ``clock``
    item (PR3b).  When no clock item is present, the line is omitted
    entirely (per spec §3.5: no clock item → no CURRENT_DATE template
    line).  The Reasoner NEVER calls ``datetime.now()`` directly.
    """
    tool_list = tools or ()
    cloud_sandbox = _cloud_sandbox_block(tool_list)
    current_date = _clock_text_from_manifest(manifest)
    variables: dict[str, str] = {
        "role": role_profile.role,
        "goal": role_profile.goal,
        "backstory": role_profile.backstory,
        "tools": tools_desc,
        "task": state.task,
        "prior_conversation": _prior_conversation_text(state),
        "context": context_lines,
        "available_skills": available_skills or "（无技能库）",
        "activated_skills": _format_activated_skills(state),
        "search_routing": "",  # PR3c: live search probe is gone.
        "cloud_sandbox": cloud_sandbox,
    }
    if current_date is not None:
        variables["current_date"] = current_date
    return variables


def _clock_text_from_manifest(manifest: ContextManifest | None) -> str | None:
    """Return the clock item's payload string, or None if absent."""
    if manifest is None:
        return None
    for item in manifest.items:
        if item.kind == "clock" and isinstance(item.payload, str):
            return item.payload
    return None


def _with_subtasks(variables: dict[str, str], state: AgentState) -> dict[str, str]:
    """Apply the manifest's ``subtasks`` item, if present.

    Pre-PR3c the subtasks were read from ``state.working_memory``; the
    spec forbids live state reads so they now come from the typed
    manifest slot (PR3c).
    """
    subtasks = _subtasks_from_manifest(state)
    if not subtasks:
        return variables
    enriched = dict(variables)
    enriched["context"] = (
        enriched["context"] + "\n\nSubtasks:\n" + "\n".join(f"- {s}" for s in subtasks)
    )
    return enriched


def _subtasks_from_manifest(state: AgentState) -> list[str]:
    """Read subtasks from the typed ``PerceiveState`` view."""
    manifest = PerceiveState.from_agent_state(state).current_manifest
    if manifest is None:
        return []
    for item in manifest.items:
        if item.kind == "subtasks" and isinstance(item.payload, list):
            return [str(x) for x in item.payload]
    return []


def _with_artifact_context(variables: dict[str, str], state: AgentState) -> dict[str, str]:
    """Inject workspace artifact summary from the manifest (PR3c).

    The pre-PR3c path called ``get_run_workspace()`` directly.  The v3
    spec forbids live workspace reads in the Reasoner; the typed
    manifest is the only source of truth.
    """
    manifest = PerceiveState.from_agent_state(state).current_manifest
    if manifest is None:
        return variables
    for item in manifest.items:
        if item.kind == "workspace_artifacts" and isinstance(item.payload, list) and item.payload:
            enriched = dict(variables)
            enriched["context"] = enriched["context"] + "\n\n" + _format_artifacts(item.payload)
            return enriched
    return variables


def _format_artifacts(payload: list[object]) -> str:
    lines: list[str] = []
    for art in payload:
        if isinstance(art, dict):
            path = art.get("path", "")
            url = art.get("url", "")
            mime = art.get("mime", "")
            size = art.get("size", 0)
            lines.append(f"- {path} ({mime}, {size}B) {url}")
    if not lines:
        return ""
    return "Workspace artifacts:\n" + "\n".join(lines)


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
        manifest = PerceiveState.from_agent_state(state).current_manifest
        variables = _role_prompt_vars(
            self.role_profile,
            self.tools_desc,
            state,
            _context_lines(state, exclude_kinds=exclusions),
            tools=self.tools,
            available_skills=self.available_skills,
            manifest=manifest,
        )
        template_name = state.active_template or _DEFAULT_TEMPLATE
        if awareness is not None:
            variables.update(build_awareness_variables(awareness))
            template_name = state.active_template or default_template_for(awareness)
        variables = _with_subtasks(variables, state)
        variables = _with_artifact_context(variables, state)
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
