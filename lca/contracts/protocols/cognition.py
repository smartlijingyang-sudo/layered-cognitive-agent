"""L1 认知 / Brain 协议 —— Reasoner / Critic / Brain 等。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Decision, Observation, Reflection
from lca.contracts.protocols.infra import LLMAdapter, Tool
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
    """确定性收尾策略：校验候选决策是否可被采纳。

    如果某个 DecisionGate 能在 LLM 生成候选之前就确定性地判定下一步（不依赖候选
    内容），应额外实现 ``SupportsShortcut`` 提供快速路径——这是可选能力，不是本
    Protocol 的必选契约，理由见 ``SupportsShortcut`` 的文档。
    """

    async def enforce(
        self,
        state: AgentState,
        decision: Decision,
    ) -> Decision: ...


@runtime_checkable
class SupportsShortcut(Protocol):
    """可选能力：允许 DecisionGate 在认知管线之前提供确定性快速路径。

    与 ``SupportsDecisionGate`` 用途相似、语义相反：

    - ``SupportsDecisionGate`` 缺失 = 配置的 guardrail 没有生效，是正确性问题，
      调用方 isinstance 探测失败必须报错。
    - ``SupportsShortcut`` 缺失只是"这个 gate 没有快速路径可提供"，正确性完全由
      必选的 ``enforce()`` 兜底；探测失败时静默走完整认知管线即可，不是错误。

    ``try_shortcut`` 不直接加进 ``DecisionGate``：``@runtime_checkable`` 的 isinstance
    检查要求 Protocol 声明的全部成员都存在，直接加会让所有结构化实现
    ``DecisionGate``（不字面继承）的第三方 gate 在 ``_resolve_decision_gate()`` 的
    ``isinstance(result, DecisionGate)`` 检查处直接 ``TypeError``，除非同步补上
    ``try_shortcut``。把一个纯性能优化变成了破坏性的必选契约，与"新增可选能力用
    ``Has*``/``Supports*`` 标记 Protocol + isinstance 探测"的既有约定
    （``HasChannel``、``HasSharedMemory``）不一致。

    ``try_shortcut`` 返回 ``None`` 的语义不是"校验失败"，是"我这层定不了，交给
    LLM"——与 ``validate() -> None`` 不同。
    """

    async def try_shortcut(self, state: AgentState) -> Decision | None: ...


@runtime_checkable
class SupportsDecisionGate(Protocol):
    """可选能力：允许在 Brain 决策链外挂一层确定性收尾校验。
    不是所有 Brain 都需要支持此能力；调用方通过
    ``isinstance(brain, SupportsDecisionGate)`` 做结构化探测，
    探测失败时应当报错，而不是静默跳过（区别于旧版 hasattr 的隐式降级）。
    """

    def install_decision_gate(self, policy: DecisionGate) -> None: ...


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
        tools: list[Tool] | None = None,
        **_: Any,
    ) -> Brain: ...
