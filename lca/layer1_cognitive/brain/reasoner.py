"""Reasoner — call LLM to generate candidate thoughts.

``SimpleReasoner`` is team-agnostic (solo / member default brain).
``SupervisorReasoner`` serves SUPERVISOR-family planes:
- consultation → hierarchical_prompt + board
- routing → routing_prompt + soft assignment log
Built at composition time by SupervisorFactory (closed object graph).

Shared prompt/LLM mechanics live as module helpers so both reasoners
stay thin and own their templates without a side catalog type.
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

_DEFAULT_TEMPLATE = "react_prompt"
_HIERARCHICAL_TEMPLATE = "hierarchical_prompt"
_ROUTING_TEMPLATE = "routing_prompt"
_EMPTY_TEAMMATES = "(无可用队友)"
_EMPTY_ASSIGNED = "(尚未委派)"
_EMPTY_CONTEXT = "(无历史上下文)"
_EMPTY_REPORTS = "(尚无成员回报)"
_KIND_EXCLUDE_NONE: frozenset[MemoryRecordKind] = frozenset()


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
    """Render the routing ledger as the supervisor's authoritative fact view."""
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
    return [await llm.complete(prompt, tools=tools) for _ in range(max(1, n))]


class SimpleReasoner(Reasoner):
    """Default Reasoner: render prompt template and call the LLM.

    Team-agnostic solo/member default. Hierarchical control-plane reads
    belong exclusively to ``SupervisorReasoner`` (ADR-0026).
    Owns prompt templates directly (dict + str.format).
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

    async def generate_candidates(self, state: AgentState, n: int = 1) -> list[str]:
        variables = _with_subtasks(
            _role_prompt_vars(
                self.role_profile,
                self.tools_desc,
                self.allowed_actions_desc,
                state,
                _context_lines(state),
            ),
            state,
        )
        template_name = state.active_template or _DEFAULT_TEMPLATE
        return await _complete_candidates(
            self.llm, self.tools, self._templates, template_name, variables, n
        )


class SupervisorReasoner(Reasoner):
    """SUPERVISOR-family reasoner for consultation and free routing planes."""

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

    @classmethod
    def from_simple(cls, base: SimpleReasoner) -> SupervisorReasoner:
        """Promote a solo reasoner at supervisor composition time."""
        return cls(
            base.llm,
            base.role_profile,
            base.tools_desc,
            tools=base.tools,
            templates=dict(base._templates),
            allowed_actions_desc=base.allowed_actions_desc,
        )

    def register_template(self, name: str, template: str) -> None:
        self._templates[name] = template

    async def generate_candidates(self, state: AgentState, n: int = 1) -> list[str]:
        from lca.contracts.session import as_consultation, as_routing

        if as_consultation(state.session) is not None:
            context = _context_lines(state)
            variables = self._consultation_vars(state, context)
            template_name = state.active_template or _HIERARCHICAL_TEMPLATE
        elif as_routing(state.session) is not None:
            # The ledger (MEMBER_REPORTS) is the authoritative delegation view;
            # drop the duplicate working-memory records from CONTEXT.
            context = _context_lines(
                state, exclude_kinds=frozenset({MemoryRecordKind.DELEGATION_RESULT})
            )
            variables = self._routing_vars(state, context)
            template_name = state.active_template or _ROUTING_TEMPLATE
        else:
            raise ValueError(
                "SupervisorReasoner requires AgentState.session (ConsultationState or RoutingState)"
            )
        variables = _with_subtasks(variables, state)
        return await _complete_candidates(
            self.llm, self.tools, self._templates, template_name, variables, n
        )

    def _consultation_vars(self, state: AgentState, context_lines: str) -> dict[str, str]:
        from lca.contracts.session import require_consultation

        consultation = require_consultation(state.session)
        variables = _role_prompt_vars(
            self.role_profile,
            self.tools_desc,
            self.allowed_actions_desc,
            state,
            context_lines,
        )
        variables["teammates"] = build_teammates_text(consultation.teammates)
        variables["member_status_text"] = consultation.member_status.as_prompt_text()
        return variables

    def _routing_vars(self, state: AgentState, context_lines: str) -> dict[str, str]:
        from lca.contracts.session import require_routing

        routing = require_routing(state.session)
        assigned = ", ".join(routing.assigned_roles) if routing.assigned_roles else _EMPTY_ASSIGNED
        variables = _role_prompt_vars(
            self.role_profile,
            self.tools_desc,
            self.allowed_actions_desc,
            state,
            context_lines,
        )
        variables["teammates"] = build_teammates_text(routing.teammates)
        variables["assigned_roles_text"] = assigned
        variables["notes"] = routing.notes or "(无)"
        variables["member_reports_text"] = build_member_reports_text(routing.results)
        return variables
