"""L3 Agent / Team unit protocols — entry shape only."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.message import AgentMessage
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile
from lca.contracts.run_context import RunContext
from lca.contracts.state import StateSnapshot


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
        self, snapshot: StateSnapshot, input: str | AgentMessage | None = None
    ) -> Result: ...

    async def cancel(self) -> None: ...


@runtime_checkable
class TeamUnit(Protocol):
    """Team entry: run an objective end-to-end."""

    async def run(self, objective: str | AgentMessage) -> Result: ...


# Transitional aliases — remove after one release cycle.
AgentEntrypoint = AgentUnit
TeamEntrypoint = TeamUnit
