"""ModularBrain —— Brain 串联 Reasoner / Parser / Pipeline / Critic。"""

from __future__ import annotations

from lca.contracts.decision import Decision, Observation, Reflection
from lca.contracts.protocols import (
    Brain,
    CandidateEvaluationPipeline,
    Critic,
    DecisionGate,
    DecisionParser,
    Reasoner,
    SkillRouter,
)
from lca.contracts.state import AgentState
from lca.layer1_cognitive.brain.candidate_evaluation_pipeline import (
    SimpleCandidateEvaluationPipeline,
)


class ModularBrain(Brain):
    """Default ``Brain``: a modular MAP-style cognitive pipeline.
    Orchestrates five stages:
    1. **Skill routing** (optional) — select an active prompt template.
    2. **Task decomposition** — break the task into subtasks.
    3. **Candidate generation** — call the Reasoner (LLM) for candidate decisions.
    4. **Decision parsing** — parse raw LLM output into ``Decision``.
    5. **Candidate evaluation** — score and select the best candidate.
    Reflection is delegated to the ``Critic`` component.

    Decompose/evaluate is always delegated to a ``CandidateEvaluationPipeline``.
    When none is injected the default ``SimpleCandidateEvaluationPipeline``
    is used — task returned as-is, best candidate selected by max confidence
    with content-aware conflict detection. Inject a custom pipeline for deeper
    evaluation.
    """

    def __init__(
        self,
        reasoner: Reasoner,
        decision_parser: DecisionParser,
        critic: Critic,
        evaluation_pipeline: CandidateEvaluationPipeline | None = None,
        skill_router: SkillRouter | None = None,
    ) -> None:
        self.reasoner = reasoner
        self.decision_parser = decision_parser
        self.critic = critic
        self.evaluation_pipeline: CandidateEvaluationPipeline = (
            evaluation_pipeline or SimpleCandidateEvaluationPipeline()
        )
        self.skill_router = skill_router
        self._decision_gate: DecisionGate | None = None

    async def think(self, state: AgentState) -> Decision:
        if self.skill_router is not None:
            state.active_template = await self.skill_router.route(state)

        subtasks = await self.evaluation_pipeline.decompose(state)
        if subtasks:
            state.working_memory["subtasks"] = list(subtasks)
        n = max(1, len(subtasks)) if len(subtasks) > 1 else 1
        raw_candidates = await self.reasoner.generate_candidates(state, n=n)
        candidates = [self.decision_parser.parse(rc, state) for rc in raw_candidates]
        decision = await self.evaluation_pipeline.evaluate(state, candidates)

        if self._decision_gate is not None:
            decision = await self._decision_gate.enforce(state, decision)
        return decision

    async def reflect(self, state: AgentState, observation: Observation) -> Reflection:
        return await self.critic.critique(state, observation)

    def install_decision_gate(self, policy: DecisionGate) -> None:
        """安装确定性收尾 guardrail，在评估结果上叠加策略校验。"""
        self._decision_gate = policy
