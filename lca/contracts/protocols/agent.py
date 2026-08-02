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
    """Composition-time budget validation strategy.

    validate raises BudgetPolicyViolation when the agent's budget
    fields are below required minimums. The caller (assembly) is
    responsible for constructing the agent with correct values before
    calling validate, or for catching the violation and correcting.
    """

    def validate(self, agent: BudgetAware) -> None: ...


@runtime_checkable
class TeamUnit(Protocol):
    """Team entry: run an objective end-to-end."""

    async def run(self, objective: str | AgentMessage) -> Result: ...
