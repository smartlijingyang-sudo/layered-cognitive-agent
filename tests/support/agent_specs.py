"""测试支持：AgentSpec 快速构造。

仅用于测试（不进 lca 包）。生产代码请用 lca.Agent 门面
或显式构造 AgentSpec。
"""

from __future__ import annotations

from lca.contracts.agent_spec import AgentSpec
from lca.contracts.protocols import LLMAdapter
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest


def make_spec(
    role: str,
    llm: LLMAdapter,
    *,
    goal: str = "g",
    backstory: str = "b",
    max_steps: int = 5,
) -> AgentSpec:
    return AgentSpec(
        profile=RoleProfile(
            role=role,
            goal=goal,
            backstory=backstory,
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        ),
        llm=llm,
        max_steps=max_steps,
    )
