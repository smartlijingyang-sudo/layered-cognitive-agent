"""L3 团队编排协议 —— 策略 / 上下文 / 共享记忆 / 聚合。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from lca.contracts.enums import MemoryLayer
from lca.contracts.member_status import MemberStatus
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols.agent import AgentUnit
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, TeamConfig


@dataclass
class TeamContext:
    """编排策略的运行时上下文，由 TeamOrchestrator 构造并传给策略实例。

    supervisor 是 AgentUnit —— 组合期由 TeamOrchestrator
    binds channel / decision gate / SupervisorReasoner; strategies only call run.
    member_status is the MemberStatus board passed through to the supervisor
    as ConsultationState by HierarchicalStrategy.
    """

    members: Sequence[AgentUnit] = field(default_factory=list)
    config: TeamConfig | None = None
    supervisor: AgentUnit | None = None
    transport: AgentTransport | None = None
    teammates: list[RoleProfile] = field(default_factory=list)
    member_status: MemberStatus | None = None
    team_id: str = ""
    shared_memory: SharedMemoryStore | None = None


@runtime_checkable
class TeamProcessStrategy(Protocol):
    """编排策略接口：每种 process 模式对应一个实现。"""

    async def run(self, context: TeamContext, objective: str) -> Result: ...


@runtime_checkable
class SharedMemoryStore(Protocol):
    """跨 Agent 共享记忆存储接口。
    按 layer 分流读写（CoALA：semantic/procedural 可共享，
    episodic/working 保持私有）。由 TeamOrchestrator 构造并注入。
    """

    def is_shared(self, layer: MemoryLayer) -> bool: ...
    def add_record(self, layer: MemoryLayer, record: MemoryRecord) -> None: ...
    def get_records(self, layer: MemoryLayer) -> list[MemoryRecord]: ...


@runtime_checkable
class Synthesizer(Protocol):
    """MoA 聚合器：将多个并行候选结果合成为一个最终结果。"""

    async def synthesize(self, objective: str, candidates: list[Result]) -> Result: ...
