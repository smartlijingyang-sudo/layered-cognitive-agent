"""Reasoner — call LLM to generate candidate thoughts."""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.enums import RoleMode
from lca.contracts.protocols import LLMAdapter, Reasoner, Tool
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import AgentState

_DEFAULT_TEMPLATE = "react_prompt"
_HIERARCHICAL_TEMPLATE = "hierarchical_prompt"


def build_teammates_text(profiles: list[RoleProfile]) -> str:
    if not profiles:
        return "(无可用队友)"
    return "\n".join(f"- role: {p.role} | goal: {p.goal}" for p in profiles)


class SimpleReasoner(Reasoner):
    """Default Reasoner: render prompt template and call the LLM.

    Manages prompt templates internally (dict + str.format) — no
    external PromptManager dependency required.
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
        template_name = self._resolve_template(state)
        if state.role_mode != RoleMode.SOLO:
            teammates_text = build_teammates_text(state.teammates)
            status_text = (
                state.member_status.as_prompt_text() if state.member_status is not None else ""
            )
            base_vars["teammates"] = teammates_text
            base_vars["member_status_text"] = status_text
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

    def _resolve_template(self, state: AgentState) -> str:
        if state.active_template:
            return state.active_template
        if state.role_mode != RoleMode.SOLO:
            return _HIERARCHICAL_TEMPLATE
        return _DEFAULT_TEMPLATE
