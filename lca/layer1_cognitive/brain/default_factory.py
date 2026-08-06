"""SimpleBrainFactory —— 默认 Brain 策略的自包含工厂（L1 实现层）。"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.protocols import Brain, LLMAdapter, Tool
from lca.contracts.protocols.action import ActionRegistryProtocol
from lca.layer1_cognitive.body.action_catalog import format_allowed_actions_desc
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
from lca.layer1_cognitive.brain.reasoner import PromptReasoner


class SimpleBrainFactory:
    """默认 Brain 策略工厂。

    组装 Reasoner → DecisionParser → Critic，
    共享 action_registry 与 Body 保持一致。
    """

    def __call__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        action_registry: ActionRegistryProtocol | None = None,
        tools: list[Tool] | None = None,
        **_ignored: Any,
    ) -> Brain:
        allowed_actions_desc = ""
        if action_registry is not None:
            allowed_actions_desc = format_allowed_actions_desc(
                action_registry.allowed_action_types()
            )

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
            allowed_actions_desc=allowed_actions_desc,
        )
        return ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(action_registry=action_registry),
            critic=SimpleCritic(),
        )
