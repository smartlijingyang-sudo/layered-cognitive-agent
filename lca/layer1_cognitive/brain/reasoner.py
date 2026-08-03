"""Reasoner — call LLM to generate candidate thoughts.

``SimpleReasoner`` is team-agnostic (solo / member default brain).
``SupervisorReasoner`` is the hierarchical-supervisor cognitive path:
always hierarchical prompt + consultation board. Installed at
composition time by ``TeamOrchestrator._bind_supervisor``.
"""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.protocols import LLMAdapter, Reasoner, Tool
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import AgentState

_DEFAULT_TEMPLATE = "react_prompt"
_HIERARCHICAL_TEMPLATE = "hierarchical_prompt"
_EMPTY_TEAMMATES = "(无可用队友)"


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
    """Hierarchical supervisor reasoner — bounded LLM discretion over consultation.

    Always uses ``hierarchical_prompt``. Requires ``state.consultation``
    (installed via ``RunContext`` by ``HierarchicalStrategy``). Which
    waiting role to consult next and how to phrase the subtask is LLM
    discretion when multiple roles remain; the decision gate enforces
    the settlement invariant after the fact.
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
        consultation = state.consultation
        if consultation is None:
            raise ValueError(
                "SupervisorReasoner requires AgentState.consultation; "
                "bind hierarchical supervisor via TeamOrchestrator / HierarchicalStrategy"
            )
        context_lines = (
            "\n".join(f"- [{r.memory_type.value}] {r.content}" for r in state.retrieved_context)
            or "(无历史上下文)"
        )
        status_text = consultation.member_status.as_prompt_text()
        base_vars = {
            "role": self.role_profile.role,
            "goal": self.role_profile.goal,
            "backstory": self.role_profile.backstory,
            "tools": self.tools_desc,
            "task": state.task,
            "context": context_lines,
            "allowed_actions": self.allowed_actions_desc,
            "teammates": build_teammates_text(consultation.teammates),
            "member_status_text": status_text,
        }
        template_name = state.active_template or _HIERARCHICAL_TEMPLATE
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
