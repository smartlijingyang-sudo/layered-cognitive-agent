"""L3 团队编排协议 —— 策略 / 上下文 / 共享记忆 / 聚合。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from lca.contracts.enums import MemoryLayer
from lca.contracts.member_status import MemberStatus
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols.agent import AgentUnit
from lca.contracts.protocols.infra import AgentTransport, Observability
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, TeamConfig
from lca.contracts.team_coordination import LeadMandate


@dataclass
class TeamContext:
    """编排策略的运行时上下文（已封闭对象图，策略只 run）。

    ``member_status`` is a board *template* for consultation mandates: each
    LeadStrategy.run creates a fresh ConsultationState from it.
    ``observability`` is shared across orchestrator and all members so the
    span tree stays on one backend.
    """

    members: Sequence[AgentUnit] = field(default_factory=list)
    config: TeamConfig | None = None
    lead: AgentUnit | None = None
    transport: AgentTransport | None = None
    teammates: list[RoleProfile] = field(default_factory=list)
    member_status: MemberStatus | None = None
    team_id: str = ""
    shared_memory: SharedMemoryStore | None = None
    observability: Observability | None = None


def team_lead_mandate(context: TeamContext) -> LeadMandate | None:
    """Read lead_mandate from context.config (contracts stay behavior-light)."""
    return context.config.lead_mandate if context.config is not None else None


@runtime_checkable
class TeamStrategy(Protocol):
    """编排策略接口：每种 coordination / lead 路径对应一个实现。"""

    async def run(self, context: TeamContext, objective: str) -> Result: ...


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
