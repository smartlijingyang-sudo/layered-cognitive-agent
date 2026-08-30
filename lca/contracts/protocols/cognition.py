"""L1 认知 / Brain 协议 —— Reasoner / Critic / Brain 等。

PR3a adds: PerceiveHub, Sensor, ContextItem, ContextManifest.
PR4 adds: PolicyFact, ExecutionEnvelope, DecisionVerdict.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.protocols.infra import LLMAdapter, Tool
from lca.contracts.protocols.memory import MemorySystem
from lca.contracts.protocols.operational_skills import SkillPackageStore


@runtime_checkable
class Sensor(Protocol):
    """A pure read-only data source for the PerceiveHub fold.

    Sensors must operate on already-staged state / journal; they must NOT
    issue live workspace reads — gates in PR6 read from the Manifest
    artifact items.  Sensors return a list of ``ContextItem`` (possibly
    empty) and raise ``SensorDisabledError`` to signal the Hub to skip them.

    The Hub handles per-Sensor exception isolation (per spec §5.5).
    """

    async def read(self, state: AgentState) -> list[ContextItem]: ...


class SensorDisabledError(RuntimeError):
    """Raised by a Sensor to signal "skip me this turn" (per spec §5.5)."""


# Backwards-compat alias — C4 renamed ``SensorDisabled`` → ``SensorDisabledError``
# for clarity. Downstream code on this branch (lca/layer1_cognitive/perceive_hub,
# tests/test_journal_reducer_apply_delta_equivalent_to_fold_events,
# tests/test_team_message_publish) still imports the old name. Restore as thin
# alias so callers keep working. Mirrors C1/C3 alias precedent.
SensorDisabled = SensorDisabledError


@runtime_checkable
class PerceiveHub(Protocol):
    """Combine ``Memory.perceive`` with a list of Sensors into a ContextManifest.

    The Hub is the SOLE emitter of ``ContextManifested`` (PR3a).  The
    fold order is fixed (per spec §5.5):

    1. Sensors (in composition order; failures isolated)
    2. Budgeter (Drop / Trim)
    3. Memory adapter (per spec §5.5)
    4. RecordGateDecided fold (PolicyFacts from the previous step)
    5. Manifest emission

    The Hub must NOT mutate ``state.history`` and must NOT mutate
    ``state.working_memory`` directly — the Reasoner never reads
    working_memory for world facts.
    """

    async def perceive(self, state: AgentState) -> ContextManifest: ...


@runtime_checkable
class PerceiveHubAssembler(Protocol):
    """Compose one PerceiveHub from profile-selected sensor contributions.

    The Perceive group service owns contribution ordering and supplies the
    resulting immutable sensor sequence.  The selected assembler owns only
    the Hub strategy, allowing profiles to replace sequential collection
    without teaching the loop or the composition root about a concrete Hub.
    """

    def assemble(
        self,
        *,
        sensors: Sequence[Sensor],
        memory: MemorySystem,
    ) -> PerceiveHub: ...


@runtime_checkable
class DecisionGateAssembler(Protocol):
    """Compose the ordered Gate contributions for one decision slot.

    A GateService owns membership, slot filtering, and ordering.  The
    selected assembler owns the strategy used to turn that sequence into one
    DecisionGate, such as a sequential chain or a profile-specific policy.
    """

    def assemble(self, *, gates: Sequence[DecisionGate]) -> DecisionGate: ...


@runtime_checkable
class Reasoner(Protocol):
    """思考生成器：基于当前状态调用 LLM 并返回完整响应（含 text + tool_calls）。"""

    async def generate_thoughts(self, state: AgentState) -> LLMResponse: ...


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
class SkillRouter(Protocol):
    """运行时动态选择 Prompt 模板 / 工具子集。"""

    async def route(self, state: AgentState) -> str: ...


@runtime_checkable
class ReasonerTemplateCatalog(Protocol):
    """Profile-selected immutable template collection used by PromptReasoner."""

    def templates(self) -> Mapping[str, str]:
        """Return all templates required by the configured reasoning strategy."""
        ...


@runtime_checkable
class BrainPromptCatalog(Protocol):
    """模型可见的工具与技能目录。

    目录内容属于认知输入，而不是 BrainComposer 的隐式实现细节。不同 Profile
    可以替换其格式、筛选策略或内容来源，但工厂必须在组合期把输入冻结为同一份
    可重放视图。
    """

    def render_tools_xml(self) -> str:
        """Render the tools visible to the selected Brain factory."""
        ...

    def render_brain_skills(self) -> str:
        """Render the compact skill catalog visible to the selected Brain factory."""
        ...


@runtime_checkable
class BrainPromptCatalogFactory(Protocol):
    """Create one profile-selected, immutable Brain prompt catalog.

    The composer resolves this factory through a capability seam and supplies
    the already-selected skill store plus Agent-local tools.  Implementations
    must not reach into ambient composition state or select a separate store.
    """

    def create(
        self,
        *,
        skill_store: SkillPackageStore,
        tools: Iterable[Tool],
    ) -> BrainPromptCatalog:
        """Build the catalog used by exactly one Agent graph composition."""
        ...


@runtime_checkable
class BrainFactory(Protocol):
    """Brain 工厂：由 NamedRegistry 按名称解析。

    显式契约：所有参数必须声明，禁止 ``**kwargs`` 吞参。
    新增工厂参数时同步更新此 Protocol 与所有实现。
    """

    def __call__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        tools: list[Tool] | None = None,
        available_skills: str = "",
    ) -> Brain: ...
