"""L1 认知 / Brain 协议 —— Reasoner / Critic / Brain 等。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Decision, Observation, Reflection
from lca.contracts.protocols.infra import LLMAdapter
from lca.contracts.role_team import RoleProfile
from lca.contracts.state import AgentState


@runtime_checkable
class Reasoner(Protocol):
    """候选方案生成器：基于当前状态产出 n 个候选 prompt。"""

    async def generate_candidates(self, state: AgentState, n: int = 1) -> list[str]: ...


@runtime_checkable
class DecisionParser(Protocol):
    """LLM 原始输出 → Decision 解析器。"""

    def parse(self, raw_output: str, state: AgentState) -> Decision: ...


@runtime_checkable
class Critic(Protocol):
    """自省评估器：根据 Observation 产出 Reflection。"""

    async def critique(self, state: AgentState, observation: Observation) -> Reflection: ...


@runtime_checkable
class Brain(Protocol):
    """Brain 顶层策略：think + reflect。"""

    async def think(self, state: AgentState) -> Decision: ...
    async def reflect(self, state: AgentState, observation: Observation) -> Reflection: ...


@runtime_checkable
class CandidateEvaluationPipeline(Protocol):
    """候选方案评估管线：封装 decompose → evaluate 两阶段认知评估。

    decompose 将任务拆解为子任务列表；evaluate 对候选决策执行
    predict → score → conflict check → arbitrate，返回最优决策。
    所有评估步骤内联实现，不再依赖外部 MAP 子模块。
    """

    async def decompose(self, state: AgentState) -> list[str]: ...
    async def evaluate(
        self,
        state: AgentState,
        candidates: list[Decision],
    ) -> Decision: ...


@runtime_checkable
class DecisionGate(Protocol):
    """确定性收尾策略：校验候选决策是否可被采纳。"""

    async def enforce(
        self,
        state: AgentState,
        decision: Decision,
    ) -> Decision: ...


@runtime_checkable
class SupportsDecisionGate(Protocol):
    """可选能力：允许在 Brain 决策链外挂一层确定性收尾校验。
    不是所有 Brain 都需要支持此能力；调用方通过
    ``isinstance(brain, SupportsDecisionGate)`` 做结构化探测，
    探测失败时应当报错，而不是静默跳过（区别于旧版 hasattr 的隐式降级）。
    """

    def install_decision_gate(self, policy: DecisionGate) -> None: ...


@runtime_checkable
class PromptManager(Protocol):
    """Prompt 模板管理：渲染 + 注册。"""

    def render(self, template_name: str, variables: dict[str, Any]) -> str: ...
    def register_template(self, name: str, template: str) -> None: ...


@runtime_checkable
class SkillRouter(Protocol):
    """运行时动态选择 Prompt 模板 / 工具子集。"""

    async def route(self, state: AgentState) -> str: ...


@runtime_checkable
class BrainFactory(Protocol):
    """Brain 工厂：由 NamedRegistry 按名称解析。"""

    def __call__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        action_registry: ActionRegistryProtocol | None = None,
        **_: Any,
    ) -> Brain: ...
