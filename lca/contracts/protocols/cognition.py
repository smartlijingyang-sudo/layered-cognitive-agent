"""L1 认知 / Brain 协议 —— Reasoner / Critic / BrainStrategy 等。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.protocols.infra import LLMAdapter
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import TypedState


@runtime_checkable
class Reasoner(Protocol):
    """候选方案生成器：基于当前状态产出 n 个候选 prompt。"""

    async def generate_candidates(self, state: TypedState, n: int = 1) -> list[str]: ...


@runtime_checkable
class DecisionParser(Protocol):
    """LLM 原始输出 → StructuredDecision 解析器。"""

    def parse(self, raw_output: str, state: TypedState) -> StructuredDecision: ...


@runtime_checkable
class Critic(Protocol):
    """自省评估器：根据 Observation 产出 Reflection。"""

    async def critique(self, state: TypedState, observation: Observation) -> Reflection: ...


@runtime_checkable
class TaskDecomposer(Protocol):
    """任务分解器：将当前状态拆分为子任务列表。"""

    async def decompose(self, state: TypedState) -> list[str]: ...


@runtime_checkable
class StatePredictor(Protocol):
    """状态预测器：预估执行某候选后的状态变化。"""

    async def predict(self, state: TypedState, candidate_action: str) -> dict[str, Any]: ...


@runtime_checkable
class StateEvaluator(Protocol):
    """状态评估器：对预测状态打分。"""

    async def score(self, state: TypedState, predicted_state: dict[str, Any]) -> float: ...


@runtime_checkable
class ConflictMonitor(Protocol):
    """冲突检测器：检查候选决策之间的矛盾。"""

    async def check(self, state: TypedState, candidates: list[StructuredDecision]) -> list[str]: ...


@runtime_checkable
class TaskCoordinator(Protocol):
    """任务协调器：在多候选中仲裁选出最终决策。"""

    async def arbitrate(
        self,
        state: TypedState,
        candidates: list[StructuredDecision],
        scores: list[float],
    ) -> StructuredDecision: ...


@runtime_checkable
class BrainStrategy(Protocol):
    """Brain 顶层策略：think + reflect + 花名册设置。"""

    async def think(self, state: TypedState) -> StructuredDecision: ...
    async def reflect(self, state: TypedState, observation: Observation) -> Reflection: ...
    def set_team_roster(self, roster_desc: str) -> None: ...


@runtime_checkable
class CandidateEvaluationPipeline(Protocol):
    """候选方案评估管线：封装 decompose → predict → score → conflict check → arbitrate。
    将原本分散在 TaskDecomposer / StatePredictor / StateEvaluator /
    ConflictMonitor / TaskCoordinator 五个浅模块中的认知评估步骤
    收敛为一个有深度的模块（ADR-0003 的深化）。
    """

    async def decompose(self, state: TypedState) -> list[str]: ...
    async def evaluate(
        self,
        state: TypedState,
        candidates: list[StructuredDecision],
    ) -> StructuredDecision: ...


@runtime_checkable
class CompletionPolicy(Protocol):
    """确定性收尾策略：校验候选决策是否可被采纳。"""

    async def enforce(
        self,
        state: TypedState,
        decision: StructuredDecision,
    ) -> StructuredDecision: ...


@runtime_checkable
class SupportsCompletionGuard(Protocol):
    """可选能力：允许在 Brain 决策链外挂一层确定性收尾校验。
    不是所有 BrainStrategy 都需要支持此能力；调用方通过
    ``isinstance(brain, SupportsCompletionGuard)`` 做结构化探测，
    探测失败时应当报错，而不是静默跳过（区别于旧版 hasattr 的隐式降级）。
    """

    def install_completion_guard(self, policy: CompletionPolicy) -> None: ...


@runtime_checkable
class PromptManager(Protocol):
    """Prompt 模板管理：渲染 + 注册。"""

    def render(self, template_name: str, variables: dict[str, Any]) -> str: ...
    def register_template(self, name: str, template: str, version: str = "1.0") -> None: ...


@runtime_checkable
class SkillRouter(Protocol):
    """运行时动态选择 Prompt 模板 / 工具子集。"""

    async def route(self, state: TypedState) -> str: ...


@runtime_checkable
class BrainFactory(Protocol):
    """BrainStrategy 工厂：由 StrategyRegistry 按名称解析。"""

    def __call__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        action_registry: ActionRegistryProtocol | None = None,
        **_: Any,
    ) -> BrainStrategy: ...
