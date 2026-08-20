"""SimpleBrainFactory —— 默认 Brain 策略的自包含工厂（L1 实现层）。"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.mechanisms import consume
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.protocols import Brain, DecisionGate, LLMAdapter, Tool
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_gates import build_workspace_agent_gate
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
from lca.layer1_cognitive.brain.reasoner import PromptReasoner


class SimpleBrainFactory:
    """默认 Brain 策略工厂。

    组装 Reasoner → Critic，不再需要 DecisionParser（原生 function calling）。
    签名与 ``BrainFactory`` Protocol 严格对齐，不吞额外参数。

    ``agent_gate_factory`` 由 plugin tree 注入（``GateService.assemble``）；
    未注入时回落到 Standard 链 ``build_workspace_agent_gate``。
    """

    def __init__(
        self,
        *,
        agent_gate_factory: Callable[[], DecisionGate] | None = None,
        critic_factory: Callable[[], SimpleCritic] | None = None,
        reasoner_cls: type[PromptReasoner] | None = None,
    ) -> None:
        self._agent_gate_factory = agent_gate_factory or build_workspace_agent_gate
        self._critic_factory = critic_factory or SimpleCritic
        self._reasoner_cls = reasoner_cls or PromptReasoner

    def __call__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        tools: list[Tool] | None = None,
        available_skills: str = "",
    ) -> Brain:
        reasoner = self._reasoner_cls(
            consume("llm", llm, PromptReasoner),
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
            critic=self._critic_factory(),
            agent_gates=self._agent_gate_factory(),
        )
