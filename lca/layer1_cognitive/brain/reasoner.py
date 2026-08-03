"""Reasoner — call LLM to generate candidate thoughts.

``SimpleReasoner`` is team-agnostic (solo / member default brain).
``SupervisorReasoner`` serves SUPERVISOR-family planes:
- consultation → hierarchical_prompt + board
- routing → routing_prompt + soft assignment log
Installed at composition time by ``SupervisorBinder``.

Shared prompt/LLM mechanics live as module helpers so both reasoners
stay thin and own their templates without a side catalog type.
"""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.protocols import LLMAdapter, Reasoner, Tool
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import AgentState

_DEFAULT_TEMPLATE = "react_prompt"
_HIERARCHICAL_TEMPLATE = "hierarchical_prompt"
_ROUTING_TEMPLATE = "routing_prompt"
_EMPTY_TEAMMATES = "(无可用队友)"
_EMPTY_ASSIGNED = "(尚未委派)"
_EMPTY_CONTEXT = "(无历史上下文)"


def build_teammates_text(profiles: list[RoleProfile]) -> str:
    if not profiles:
        return _EMPTY_TEAMMATES
    return "\n".join(f"- role: {p.role} | goal: {p.goal}" for p in profiles)


def _context_lines(state: AgentState) -> str:
    return (
        "\n".join(f"- [{r.memory_type.value}] {r.content}" for r in state.retrieved_context)
        or _EMPTY_CONTEXT
    )


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
        context = _context_lines(state)
        if state.consultation is not None:
            variables = self._consultation_vars(state, context)
            template_name = state.active_template or _HIERARCHICAL_TEMPLATE
        elif state.routing is not None:
            variables = self._routing_vars(state, context)
            template_name = state.active_template or _ROUTING_TEMPLATE
        else:
            raise ValueError(
                "SupervisorReasoner requires AgentState.consultation or .routing; "
                "bind via TeamOrchestrator / HierarchicalStrategy"
            )
        variables = _with_subtasks(variables, state)
        return await _complete_candidates(
            self.llm, self.tools, self._templates, template_name, variables, n
        )

    def _consultation_vars(self, state: AgentState, context_lines: str) -> dict[str, str]:
        consultation = state.consultation
        if consultation is None:
            raise ValueError("consultation session required")
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
        routing = state.routing
        if routing is None:
            raise ValueError("routing session required")
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
        return variables
