"""ModularBrain —— 实现 BrainStrategy 协议，串联 MAP 五模块 + Reasoner + Critic + DecisionParser。"""

from __future__ import annotations

from contracts.state import TypedState
from contracts.decision import StructuredDecision, Observation, Reflection
from layer1_cognitive.brain.reasoner import SimpleReasoner
from layer1_cognitive.brain.critic import SimpleCritic
from layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from layer1_cognitive.brain.map_modules import (
    SimpleTaskDecomposer,
    SimpleStatePredictor,
    SimpleStateEvaluator,
    SimpleConflictMonitor,
    SimpleTaskCoordinator,
)


class ModularBrain:
    """
    think() 内部串联:
    Reasoner -> TaskDecomposer -> StatePredictor -> StateEvaluator -> ConflictMonitor -> TaskCoordinator -> DecisionParser

    reflect() 内部调用 Critic。
    """

    def __init__(
        self,
        reasoner: SimpleReasoner,
        decision_parser: SimpleDecisionParser,
        critic: SimpleCritic,
        task_decomposer: SimpleTaskDecomposer,
        state_predictor: SimpleStatePredictor,
        state_evaluator: SimpleStateEvaluator,
        conflict_monitor: SimpleConflictMonitor,
        task_coordinator: SimpleTaskCoordinator,
    ):
        self.reasoner = reasoner
        self.decision_parser = decision_parser
        self.critic = critic
        self.task_decomposer = task_decomposer
        self.state_predictor = state_predictor
        self.state_evaluator = state_evaluator
        self.conflict_monitor = conflict_monitor
        self.task_coordinator = task_coordinator

    async def think(self, state: TypedState) -> StructuredDecision:
        _subtasks = await self.task_decomposer.decompose(state)
        raw_candidates = await self.reasoner.generate_candidates(state, n=1)
        candidates = [self.decision_parser.parse(rc, state) for rc in raw_candidates]

        predicted = [await self.state_predictor.predict(state, c.rationale) for c in candidates]
        scores = [await self.state_evaluator.score(state, p) for p in predicted]
        conflicts = await self.conflict_monitor.check(state, candidates)
        if conflicts:
            print(f"  [ConflictMonitor] 检测到冲突: {conflicts}")

        return await self.task_coordinator.arbitrate(state, candidates, scores)

    async def reflect(self, state: TypedState, observation: Observation) -> Reflection:
        return await self.critic.critique(state, observation)
