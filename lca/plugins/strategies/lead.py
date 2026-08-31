"""Lead strategy factory — registers into team_strategies."""

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
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_LEAD, LeadMandate
from lca.contracts.protocols import TeamAssembly
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.journal.spec import LeadSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_DUTY_MANDATES: frozenset[LeadMandate] = frozenset({LeadMandate.CONSULT, LeadMandate.BOARD})


def build_lead_strategy(assembly: TeamAssembly) -> Any:
    from lca.agent.orchestration_strategies import LeadStrategy
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
