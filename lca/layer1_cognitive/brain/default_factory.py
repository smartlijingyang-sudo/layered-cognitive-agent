"""SimpleBrainFactory —— 默认 Brain 策略的自包含工厂（L1 实现层）。"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.protocols import Brain, LLMAdapter, Tool
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_gates import build_workspace_agent_gate
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
from lca.layer1_cognitive.brain.reasoner import PromptReasoner


class SimpleBrainFactory:
    """默认 Brain 策略工厂。

    组装 Reasoner → Critic，不再需要 DecisionParser（原生 function calling）。
    """

    def __call__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        tools: list[Tool] | None = None,
        available_skills: str = "",
        **_ignored: Any,
    ) -> Brain:
        reasoner = PromptReasoner(
            llm,
            role_profile,
            tools_desc,
            tools=tools,
            templates={
                "react_prompt": load_builtin_prompt("react_prompt"),
                "hierarchical_prompt": load_builtin_prompt("hierarchical_prompt"),
                "routing_prompt": load_builtin_prompt("routing_prompt"),
            },
            available_skills=available_skills,
        )
        return ModularBrain(
            reasoner=reasoner,
            critic=SimpleCritic(),
            agent_gates=build_workspace_agent_gate(),
        )
