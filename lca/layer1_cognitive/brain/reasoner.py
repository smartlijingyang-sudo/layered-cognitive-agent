"""Reasoner — call LLM to generate candidate thoughts.

``SimpleReasoner`` is team-agnostic (solo / member default brain).
``SupervisorReasoner`` serves SUPERVISOR-family planes:
- consultation → hierarchical_prompt + board
- routing → routing_prompt + soft assignment log
Installed at composition time by ``SupervisorBinder``.
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


def build_teammates_text(profiles: list[RoleProfile]) -> str:
    if not profiles:
        return _EMPTY_TEAMMATES
    return "\n".join(f"- role: {p.role} | goal: {p.goal}" for p in profiles)


class SimpleReasoner(Reasoner):
    """Default Reasoner: render prompt template and call the LLM.

    Team-agnostic solo/member default. Hierarchical control-plane reads
    belong exclusively to ``SupervisorReasoner`` (ADR-0026).
    Manages prompt templates internally (dict + str.format).
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
        context_lines = (
            "\n".join(f"- [{r.memory_type.value}] {r.content}" for r in state.retrieved_context)
            or "(无历史上下文)"
        )
        base_vars = {
            "role": self.role_profile.role,
            "goal": self.role_profile.goal,
            "backstory": self.role_profile.backstory,
            "tools": self.tools_desc,
            "task": state.task,
            "context": context_lines,
            "allowed_actions": self.allowed_actions_desc,
        }
        template_name = state.active_template or _DEFAULT_TEMPLATE
        subtasks = state.working_memory.get("subtasks")
        if subtasks:
            base_vars["context"] = (
                base_vars["context"] + "\n\nSubtasks:\n" + "\n".join(f"- {s}" for s in subtasks)
            )
        prompt = self._templates[template_name].format(**base_vars)
        candidates = []
        for _ in range(max(1, n)):
            candidates.append(await self.llm.complete(prompt, tools=self.tools))
        return candidates


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
        context_lines = (
            "\n".join(f"- [{r.memory_type.value}] {r.content}" for r in state.retrieved_context)
            or "(无历史上下文)"
        )
        if state.consultation is not None:
            base_vars = self._consultation_vars(state, context_lines)
            template_name = state.active_template or _HIERARCHICAL_TEMPLATE
        elif state.routing is not None:
            base_vars = self._routing_vars(state, context_lines)
            template_name = state.active_template or _ROUTING_TEMPLATE
        else:
            raise ValueError(
                "SupervisorReasoner requires AgentState.consultation or .routing; "
                "bind via TeamOrchestrator / HierarchicalStrategy"
            )
        subtasks = state.working_memory.get("subtasks")
        if subtasks:
            base_vars["context"] = (
                base_vars["context"] + "\n\nSubtasks:\n" + "\n".join(f"- {s}" for s in subtasks)
            )
        prompt = self._templates[template_name].format(**base_vars)
        candidates = []
        for _ in range(max(1, n)):
            candidates.append(await self.llm.complete(prompt, tools=self.tools))
        return candidates

    def _consultation_vars(self, state: AgentState, context_lines: str) -> dict[str, str]:
        consultation = state.consultation
        if consultation is None:
            raise ValueError("consultation session required")
        return {
            "role": self.role_profile.role,
            "goal": self.role_profile.goal,
            "backstory": self.role_profile.backstory,
            "tools": self.tools_desc,
            "task": state.task,
            "context": context_lines,
            "allowed_actions": self.allowed_actions_desc,
            "teammates": build_teammates_text(consultation.teammates),
            "member_status_text": consultation.member_status.as_prompt_text(),
        }

    def _routing_vars(self, state: AgentState, context_lines: str) -> dict[str, str]:
        routing = state.routing
        if routing is None:
            raise ValueError("routing session required")
        assigned = ", ".join(routing.assigned_roles) if routing.assigned_roles else _EMPTY_ASSIGNED
        return {
            "role": self.role_profile.role,
            "goal": self.role_profile.goal,
            "backstory": self.role_profile.backstory,
            "tools": self.tools_desc,
            "task": state.task,
            "context": context_lines,
            "allowed_actions": self.allowed_actions_desc,
            "teammates": build_teammates_text(routing.teammates),
            "assigned_roles_text": assigned,
            "notes": routing.notes or "(无)",
        }
