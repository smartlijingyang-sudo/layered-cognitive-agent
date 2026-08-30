"""L3 团队编排契约 —— 封闭策略与布线类型（ADR-0034）。

本质模型：团队在组合期被编译成封闭的 ``TeamStrategy``，运行期没有
上下文包——策略自己就是团队。``TeamStage`` / ``TeamAssembly`` /
``MemberInvoker`` 是组合期布线类型，不属于运行期领域概念。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.result import Result
from lca.contracts.protocols.collaboration.agent import AgentUnit
from lca.contracts.protocols.journal.spec import DEFAULT_DELEGATE_MAX_ATTEMPTS, Governance


@runtime_checkable
class TeamStrategy(Protocol):
    """编排策略接口：构造期闭合，运行期只 ``run(objective)``（ADR-0034）。

    每种 Governance（LeadSpec | Coordination）经注册表工厂闭合为一个实现；
    策略所需的一切（成员 / 调用通道 / lead / 轮次参数）在构造期注入。
    """

    async def run(self, objective: str) -> Result: ...


@runtime_checkable
class MemberInvoker(Protocol):
    """策略调用成员的唯一通道 —— 组合期绑定 transport 的布线协议（ADR-0034）。

    策略只认「成员 + 任务」，不认 transport；通道在组合期闭合注入，
    角色合法性由组合期 fail-fast 保证。
    """

    async def invoke(self, member: AgentUnit, task: str, *, caller_role: str = "") -> Result: ...


@dataclass(frozen=True)
class TeamStage:
    """协调型策略的行动舞台：成员 + 调用通道（布线类型，非领域概念）。"""

    members: tuple[AgentUnit, ...]
    invoker: MemberInvoker


@dataclass(frozen=True)
class TeamAssembly:
    """策略工厂 resolve 期的只读装配视图（仅存在于组合期；布线类型）。

    ``lead`` 仅当 governance 为 LeadSpec 时非 None；工厂从中取所需闭合
    策略，运行期不出现本对象。
    """

    governance: Governance
    stage: TeamStage
    lead: AgentUnit | None = None
    delegate_max_attempts: int = DEFAULT_DELEGATE_MAX_ATTEMPTS


@runtime_checkable
class SharedMemoryStore(Protocol):
    """跨 Agent 共享记忆存储接口。
    按 layer 分流读写（CoALA：semantic/procedural 可共享，
    episodic/working 保持私有）。
    """

    def is_shared(self, layer: MemoryLayer) -> bool: ...
    def add_record(self, layer: MemoryLayer, record: MemoryRecord) -> None: ...
    def get_records(self, layer: MemoryLayer) -> list[MemoryRecord]: ...


@runtime_checkable
class Synthesizer(Protocol):
    """MoA 聚合器：将多个并行候选结果合成为一个最终结果。"""

    async def synthesize(self, objective: str, candidates: list[Result]) -> Result: ...
