"""Lead strategy factory — registers into team_strategies.

同文件承载 LeadStrategy —— 有主导者团队路径（ADR-0030 / ADR-0034 /
ADR-0035）。构造期闭合：持有封闭 lead agent + 名册 + 可选咨询义务模板
（board 为 None 即自由 routing）。策略每次 run 新建 TeamAwareness——
单一类型，无会话分裂，不从任何运行期上下文解包——lead 与 coordination
同为 Governance。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import STRATEGIES
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.budget import DEFAULT_MIN_USABLE_PARTIAL_CHARS
from lca.contracts.models.core.result import Result
from lca.contracts.models.team.member_status import MemberStatus
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.models.team.team_awareness import ConsultDuty, TeamAwareness
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_LEAD, LeadMandate
from lca.contracts.protocols import AgentUnit, TeamAssembly, TeamStrategy
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.journal.spec import LeadSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_DUTY_MANDATES: frozenset[LeadMandate] = frozenset({LeadMandate.CONSULT, LeadMandate.BOARD})


class LeadStrategy(TeamStrategy):
    """Lead path: fresh awareness per run, then execute the closed lead agent."""

    def __init__(
        self,
        lead: AgentUnit,
        roster: tuple[RoleProfile, ...],
        board: MemberStatus | None,
        delegate_max_attempts: int,
        min_usable_partial_chars: int = DEFAULT_MIN_USABLE_PARTIAL_CHARS,
    ) -> None:
        self._lead = lead
        self._roster = roster
        self._board = board
        self._delegate_max_attempts = delegate_max_attempts
        self._min_usable_partial_chars = min_usable_partial_chars

    async def run(self, objective: str) -> Result:
        duty = (
            ConsultDuty(
                member_status=self._board,
                max_attempts=self._delegate_max_attempts,
                min_usable_partial_chars=self._min_usable_partial_chars,
            )
            if self._board is not None
            else None
        )
        awareness = TeamAwareness(teammates=list(self._roster), consult_duty=duty)
        return await self._lead.run(objective, RunContext(team_awareness=awareness))


def build_lead_strategy(assembly: TeamAssembly) -> Any:
    from lca.cognition.member_status import InMemoryMemberStatus

    governance = assembly.governance
    if not isinstance(governance, LeadSpec) or assembly.lead is None:
        raise TypeError(f"strategy {STRATEGY_KEY_LEAD!r} requires LeadSpec governance")
    members = assembly.stage.members
    roster = tuple(member.role_profile for member in members)
    role_order = tuple(member.role_profile.role for member in members)
    board = (
        InMemoryMemberStatus(role_order=role_order)
        if governance.mandate in _DUTY_MANDATES
        else None
    )
    return LeadStrategy(
        lead=assembly.lead,
        roster=roster,
        board=board,
        delegate_max_attempts=assembly.delegate_max_attempts,
    )


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.lead",
    requires=[STRATEGIES.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    functional_group=FunctionalGroup.G8_COLLAB,
    description="Register lead TeamStrategy factory.",
    test_suite="tests/test_orchestration_coverage.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("strategy_lead.checked", "strategy_lead.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(STRATEGIES.key, STRATEGY_KEY_LEAD, build_lead_strategy)
