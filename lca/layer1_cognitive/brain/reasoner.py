"""Reasoner —— 调用 LLM 生成候选思路。"""

from __future__ import annotations

from lca.contracts.protocols import LLMAdapter, PromptManager, Reasoner
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import TypedState

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

HIERARCHICAL_DELEGATE_TEMPLATE = """\
ROLE: {role}
GOAL: {goal}
BACKSTORY: {backstory}
AVAILABLE_TOOLS: {tools}
TEAM_ROSTER:
{team_roster}
USER_TASK: {task}
CONTEXT:
{context}

你是团队 Supervisor。你可以选择以下行动之一：
1. use_tool — 调用工具（需附带 tool_name / arguments）
2. delegate — 将子任务委派给队友（需附带 target_role / subtask / rationale）
3. respond — 直接回复用户（需附带 response_text）
4. stop — 任务已完成

请以 JSON 输出下一步 StructuredDecision，必须包含字段：action_type, rationale, confidence。
当 action_type 为 "delegate" 时，还必须包含 target_role 和 subtask。
"""


def build_team_roster(profiles: list[RoleProfile]) -> str:
    """从 RoleProfile 列表拼接团队花名册文本，渲染进 Supervisor prompt。"""
    if not profiles:
        return "(无可用队友)"
    return "\n".join(f"- role: {p.role} | goal: {p.goal}" for p in profiles)


class SimpleReasoner(Reasoner):
    """调用 LLM 生成候选行动思路。"""

    def __init__(
        self,
        llm: LLMAdapter,
        prompt_manager: PromptManager,
        role_profile: RoleProfile,
        tools_desc: str,
        team_roster: str | None = None,
    ):
        self.llm = llm
        self.prompt_manager = prompt_manager
        self.role_profile = role_profile
        self.tools_desc = tools_desc
        self.team_roster = team_roster

    def set_team_roster(self, roster_desc: str) -> None:
        self.team_roster = roster_desc

    async def generate_candidates(self, state: TypedState, n: int = 1) -> list[str]:
        context_lines = (
            "\n".join(f"- [{r.memory_type}] {r.content}" for r in state.retrieved_context)
            or "(无历史上下文)"
        )
        base_vars: dict[str, str] = {
            "role": self.role_profile.role,
            "goal": self.role_profile.goal,
            "backstory": self.role_profile.backstory,
            "tools": self.tools_desc,
            "task": state.task,
            "context": context_lines,
        }

        if self.team_roster is not None:
            template_name = "hierarchical_prompt"
            base_vars["team_roster"] = self.team_roster
        else:
            template_name = "react_prompt"

        prompt = self.prompt_manager.render(template_name, base_vars)
        raw = await self.llm.complete(prompt)
        return [raw]
