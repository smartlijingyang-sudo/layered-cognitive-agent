"""ModularBrain —— 实现 BrainStrategy 协议，串联 CandidateEvaluationPipeline + Reasoner + Critic + DecisionParser。"""

from __future__ import annotations

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.protocols import (
    BrainStrategy,
    CandidateEvaluationPipeline,
    Critic,
    DecisionParser,
    Reasoner,
    SkillRouter,
)
from lca.contracts.state import TypedState


class ModularBrain(BrainStrategy):
    """
    think() 内部串联:
    Reasoner -> CandidateEvaluationPipeline -> DecisionParser

    reflect() 内部调用 Critic。
    """

    def __init__(
        self,
        reasoner: Reasoner,
        decision_parser: DecisionParser,
        critic: Critic,
        evaluation_pipeline: CandidateEvaluationPipeline,
        skill_router: SkillRouter | None = None,
    ):
        self.reasoner = reasoner
        self.decision_parser = decision_parser
        self.critic = critic
        self.evaluation_pipeline = evaluation_pipeline
        self.skill_router = skill_router

    async def think(self, state: TypedState) -> StructuredDecision:
        if self.skill_router is not None:
            template_name = await self.skill_router.route(state)
            state.active_template = template_name

        await self.evaluation_pipeline.decompose(state)
        raw_candidates = await self.reasoner.generate_candidates(state, n=1)
        candidates = [self.decision_parser.parse(rc, state) for rc in raw_candidates]

        return await self.evaluation_pipeline.evaluate(state, candidates)

    async def reflect(self, state: TypedState, observation: Observation) -> Reflection:
        return await self.critic.critique(state, observation)

    def set_team_roster(self, roster_desc: str) -> None:
        if hasattr(self.reasoner, "set_team_roster"):
            self.reasoner.set_team_roster(roster_desc)
        elif hasattr(self.reasoner, "team_roster"):
            self.reasoner.team_roster = roster_desc
