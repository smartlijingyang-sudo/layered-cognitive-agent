"""Reasoner —— 调用 LLM 生成候选思路。"""

from __future__ import annotations

from lca.contracts.protocols import LLMAdapter, PromptManager, Reasoner
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import TypedState
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt

DEFAULT_REACT_TEMPLATE: str = load_builtin_prompt("react_prompt")
HIERARCHICAL_DELEGATE_TEMPLATE: str = load_builtin_prompt("hierarchical_prompt")
_DEFAULT_TEMPLATE = "react_prompt"
_HIERARCHICAL_TEMPLATE = "hierarchical_prompt"


def build_team_roster(profiles: list[RoleProfile]) -> str:
    if not profiles:
        return "(无可用队友)"
    return "\n".join(f"- role: {p.role} | goal: {p.goal}" for p in profiles)


class SimpleReasoner(Reasoner):
    def __init__(
        self,
        llm: LLMAdapter,
        prompt_manager: PromptManager,
        role_profile: RoleProfile,
        tools_desc: str,
        team_roster: str | None = None,
        allowed_actions_desc: str = "",
    ) -> None:
        self.llm = llm
        self.prompt_manager = prompt_manager
        self.role_profile = role_profile
        self.tools_desc = tools_desc
        self.team_roster = team_roster
        self.allowed_actions_desc = allowed_actions_desc

    def set_team_roster(self, roster_desc: str) -> None:
        self.team_roster = roster_desc

    async def generate_candidates(self, state: TypedState, n: int = 1) -> list[str]:
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
        if self.team_roster is not None:
            base_vars["team_roster"] = self.team_roster
            base_vars["team_progress"] = state.team_progress_text or ""
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

    def _resolve_template(self, state: TypedState) -> str:
        if state.active_template:
            return state.active_template
        if self.team_roster is not None:
            return _HIERARCHICAL_TEMPLATE
        return _DEFAULT_TEMPLATE
