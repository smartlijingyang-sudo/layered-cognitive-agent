"""可替换的认知子流程协议。

``Brain`` 是面向阶段执行器的稳定门面；本模块进一步将其内部原先固定在
``ModularBrain`` 中的 Think 与 Reflect 编排提取为两个独立的 L1 原语。二者由
组合层显式注入，并且只产生 ``Decision`` 或 ``Reflection`` 候选，不拥有外部
world effect 权力。

这两个协议有意不包含 Journal、EffectGateway、phase cursor 或 runtime control。
状态的合法投影仍必须经过 ``Reducer``，而执行、提交和图遍历仍属于声明式运行时
内核。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.think.cognition import (
    Critic,
    DecisionGate,
    Reasoner,
    SkillRouter,
)

if TYPE_CHECKING:
    from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
    from lca.contracts.protocols.state.reducer import Reducer


@runtime_checkable
class CognitiveThinkPipeline(Protocol):
    """Turn a staged state into one governed ``Decision`` candidate.

    Implementations may orchestrate the existing shortcut, skill routing,
    reasoning, classification and decision-gate primitives. They must not
    perform external effects or directly mutate ``AgentState``; the sole
    permitted state projection collaborator is the injected ``Reducer``.
    """

    async def decide(
        self,
        *,
        state: AgentState,
        reasoner: Reasoner,
        classifier: DecisionClassifier,
        skill_router: SkillRouter | None,
        decision_gate: DecisionGate | None,
        agent_gates: DecisionGate | None,
        reducer: Reducer | None,
    ) -> Decision:
        """Return the profile-governed decision for the current turn."""
        ...


@runtime_checkable
class CognitiveReflectionPipeline(Protocol):
    """Turn an observation into one reflection candidate.

    The explicit ``critic`` collaborator preserves the existing optional
    critic seam while making the fallback reflection semantics profile
    selectable instead of an implicit private ``Brain`` method.
    """

    async def reflect(
        self,
        *,
        state: AgentState,
        observation: Observation,
        critic: Critic | None,
    ) -> Reflection:
        """Return the profile-governed reflection for the observation."""
        ...


__all__ = ["CognitiveReflectionPipeline", "CognitiveThinkPipeline"]
