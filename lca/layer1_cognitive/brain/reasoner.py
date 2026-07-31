"""Reasoner — call LLM to generate candidate thoughts."""

from __future__ import annotations

from lca.contracts.protocols import LLMAdapter, PromptManager, Reasoner
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import AgentState
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt

DEFAULT_REACT_TEMPLATE: str = load_builtin_prompt("react_prompt")
HIERARCHICAL_DELEGATE_TEMPLATE: str = load_builtin_prompt("hierarchical_prompt")
_DEFAULT_TEMPLATE = "react_prompt"
_HIERARCHICAL_TEMPLATE = "hierarchical_prompt"


def build_teammates_text(profiles: list[RoleProfile]) -> str:
    if not profiles:
        return "(无可用队友)"
    return "\n".join(f"- role: {p.role} | goal: {p.goal}" for p in profiles)


class SimpleReasoner(Reasoner):
    """Default Reasoner: render prompt template and call the LLM."""

    def __init__(
        self,
        llm: LLMAdapter,
        prompt_manager: PromptManager,
        role_profile: RoleProfile,
        tools_desc: str,
        teammates_text: str | None = None,
        allowed_actions_desc: str = "",
    ) -> None:
        self.llm = llm
        self.prompt_manager = prompt_manager
        self.role_profile = role_profile
        self.tools_desc = tools_desc
        self.teammates_text = teammates_text
        self.allowed_actions_desc = allowed_actions_desc

    def set_teammates(self, teammates_text: str) -> None:
        self.teammates_text = teammates_text

    async def generate_candidates(self, state: AgentState, n: int = 1) -> list[str]:
        context_lines = (
            "\n".join(f"- [{r.memory_type}] {r.content}" for r in state.retrieved_context)
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
        if self.teammates_text is not None:
            status_text = (
                state.member_status.as_prompt_text() if state.member_status is not None else ""
            )
            base_vars["teammates"] = self.teammates_text
            base_vars["member_status_text"] = status_text
            # Backward-compatible keys if custom templates still use old names
            base_vars["teammates_text"] = self.teammates_text
        subtasks = state.working_memory.get("subtasks")
        if subtasks:
            base_vars["context"] = (
                base_vars["context"] + "\n\nSubtasks:\n" + "\n".join(f"- {s}" for s in subtasks)
            )
        prompt = self.prompt_manager.render(template_name, base_vars)
        candidates = []
        for _ in range(max(1, n)):
            candidates.append(await self.llm.complete(prompt))
        return candidates

    def _resolve_template(self, state: AgentState) -> str:
        if state.active_template:
            return state.active_template
        if self.teammates_text is not None:
            return _HIERARCHICAL_TEMPLATE
        return _DEFAULT_TEMPLATE
