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
from lca.contracts.protocols.capabilities import AcceptsTeammates
from lca.contracts.state import AgentState
from lca.layer1_cognitive.brain.candidate_evaluation_pipeline import (
    GuardedCandidateEvaluationPipeline,
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
    """

    def __init__(
        self,
        reasoner: Reasoner,
        decision_parser: DecisionParser,
        critic: Critic,
        evaluation_pipeline: CandidateEvaluationPipeline,
        skill_router: SkillRouter | None = None,
    ) -> None:
        self.reasoner = reasoner
        self.decision_parser = decision_parser
        self.critic = critic
        self.evaluation_pipeline = evaluation_pipeline
        self.skill_router = skill_router

    async def think(self, state: AgentState) -> Decision:
        if self.skill_router is not None:
            state.active_template = await self.skill_router.route(state)
        subtasks = await self.evaluation_pipeline.decompose(state)
        if subtasks:
            state.working_memory["subtasks"] = list(subtasks)
        n = max(1, len(subtasks)) if len(subtasks) > 1 else 1
        raw_candidates = await self.reasoner.generate_candidates(state, n=n)
        candidates = [self.decision_parser.parse(rc, state) for rc in raw_candidates]
        decision: Decision = await self.evaluation_pipeline.evaluate(state, candidates)
        return decision

    async def reflect(self, state: AgentState, observation: Observation) -> Reflection:
        return await self.critic.critique(state, observation)

    def set_teammates(self, teammates_text: str) -> None:
        if isinstance(self.reasoner, AcceptsTeammates):
            self.reasoner.set_teammates(teammates_text)

    def install_decision_gate(self, policy: DecisionGate) -> None:
        """在内部评估管线外挂一层确定性收尾 guardrail（Brain 自管内省，外部不穿透）。
        装饰器的构造细节（``GuardedCandidateEvaluationPipeline``）留在 L1，
        调用方只需要提供 policy，不需要知道内部是用管线实现的。
        """
        self.evaluation_pipeline = GuardedCandidateEvaluationPipeline(
            self.evaluation_pipeline, policy
        )
