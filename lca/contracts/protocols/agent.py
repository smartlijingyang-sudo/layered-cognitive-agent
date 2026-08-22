"""L3 Agent / Team unit protocols — entry shape only."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.budget import BudgetLimits
from lca.contracts.models.core.message import AgentMessage
from lca.contracts.models.core.result import Result
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols.declarative_phase_graph import DeclarativeCheckpoint


@runtime_checkable
class AgentUnit(Protocol):
    """Single-agent entry: run / resume / cancel."""

    role_profile: RoleProfile

    async def run(
        self,
        task: str | AgentMessage,
        ctx: RunContext | None = None,
    ) -> Result: ...

    async def resume(
        self, checkpoint: DeclarativeCheckpoint, input: str | AgentMessage | None = None
    ) -> Result: ...

    async def cancel(self) -> None: ...


@runtime_checkable
class BudgetAware(Protocol):
    """Agent that exposes budget fields for policy validation.

    CognitiveAgent satisfies this protocol; the Protocol decouples
    budget validation from the concrete agent class so that
    BudgetPolicy implementations can live in contracts.
    """

    max_steps: int
    max_wall_clock_seconds: int | None
    role_profile: RoleProfile


@runtime_checkable
class BudgetPolicy(Protocol):
    """组合时预算解析策略——单一真相源。

    resolve 返回该 agent 在其角色下应得的有效预算值。
    调用方 apply 返回值，不重算阈值。
    """

    def resolve(self, agent: BudgetAware) -> BudgetLimits: ...


@runtime_checkable
class TeamUnit(Protocol):
    """Team entry: run an objective end-to-end."""

    async def run(self, objective: str | AgentMessage) -> Result: ...
