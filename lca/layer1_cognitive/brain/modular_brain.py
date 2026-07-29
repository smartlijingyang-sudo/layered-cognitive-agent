"""ModularBrain —— BrainStrategy 串联 Reasoner / Parser / Pipeline / Critic。"""

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

    async def think(self, state: TypedState) -> StructuredDecision:
        if self.skill_router is not None:
            state.active_template = await self.skill_router.route(state)
        subtasks = await self.evaluation_pipeline.decompose(state)
        if subtasks:
            state.working_memory["subtasks"] = list(subtasks)
        n = max(1, len(subtasks)) if len(subtasks) > 1 else 1
        raw_candidates = await self.reasoner.generate_candidates(state, n=n)
        candidates = [self.decision_parser.parse(rc, state) for rc in raw_candidates]
        decision: StructuredDecision = await self.evaluation_pipeline.evaluate(state, candidates)
        return decision

    async def reflect(self, state: TypedState, observation: Observation) -> Reflection:
        return await self.critic.critique(state, observation)

    def set_team_roster(self, roster_desc: str) -> None:
        setter = getattr(self.reasoner, "set_team_roster", None)
        if callable(setter):
            setter(roster_desc)
        elif hasattr(self.reasoner, "team_roster"):
            self.reasoner.team_roster = roster_desc
