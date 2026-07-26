"""Reasoner —— 调用 LLM 生成候选思路。"""

from __future__ import annotations

from typing import Any

from lca.contracts.state import TypedState
from lca.contracts.role_team import RoleProfile
from lca.contracts.protocols import LLMAdapter, PromptManager, Reasoner


DEFAULT_REACT_TEMPLATE = """\
ROLE: {role}
GOAL: {goal}
BACKSTORY: {backstory}
AVAILABLE_TOOLS: {tools}
USER_TASK: {task}
CONTEXT:
{context}

请以 JSON 输出下一步 StructuredDecision（字段：action_type/tool_name/arguments/response_text/rationale/confidence）。
"""


class SimpleReasoner(Reasoner):
    """调用 LLM 生成候选行动思路。"""

    def __init__(
        self,
        llm: LLMAdapter,
        prompt_manager: PromptManager,
        role_profile: RoleProfile,
        tools_desc: str,
    ):
        self.llm = llm
        self.prompt_manager = prompt_manager
        self.role_profile = role_profile
        self.tools_desc = tools_desc

    async def generate_candidates(self, state: TypedState, n: int = 1) -> list[str]:
        context_lines = "\n".join(
            f"- [{r.memory_type}] {r.content}" for r in state.retrieved_context
        ) or "(无历史上下文)"
        prompt = self.prompt_manager.render("react_prompt", {
            "role": self.role_profile.role,
            "goal": self.role_profile.goal,
            "backstory": self.role_profile.backstory,
            "tools": self.tools_desc,
            "task": state.task,
            "context": context_lines,
        })
        raw = await self.llm.complete(prompt)
        return [raw]
