"""DefaultBrainFactory —— 默认 Brain 策略的自包含工厂。

将 build_default_brain 的逻辑从 assembly.py 内聚到此处，
消除 defaults.py → assembly.py 的反向依赖。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.protocols import BrainStrategy, LLMAdapter
from lca.contracts.role_team import RoleProfile
from lca.layer1_cognitive.body.action_catalog import format_allowed_actions_desc
from lca.layer1_cognitive.brain.candidate_evaluation_pipeline import (
    SimpleCandidateEvaluationPipeline,
)
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.prompt_manager import SimplePromptManager
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner


class DefaultBrainFactory:
    """默认 Brain 策略工厂。

    组装 PromptManager → Reasoner → DecisionParser → Critic →
    CandidateEvaluationPipeline，共享 action_registry 与 Body 保持一致。
    """

    def __call__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        action_registry: ActionRegistryProtocol | None = None,
        **_ignored: Any,
    ) -> BrainStrategy:
        prompt_manager = SimplePromptManager()
        prompt_manager.register_template("react_prompt", load_builtin_prompt("react_prompt"))
        prompt_manager.register_template(
            "hierarchical_prompt", load_builtin_prompt("hierarchical_prompt")
        )

        allowed_actions_desc = ""
        if action_registry is not None:
            allowed_actions_desc = format_allowed_actions_desc(
                action_registry.allowed_action_types()
            )

        reasoner = SimpleReasoner(
            llm,
            prompt_manager,
            role_profile,
            tools_desc,
            allowed_actions_desc=allowed_actions_desc,
        )
        return ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(action_registry=action_registry),
            critic=SimpleCritic(),
            evaluation_pipeline=SimpleCandidateEvaluationPipeline(),
        )
