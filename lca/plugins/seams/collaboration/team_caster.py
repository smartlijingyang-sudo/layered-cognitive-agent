"""Profile-selected TeamCaster provider for automatic Team casting.

The casting policy is independent of the gateway mode adapter and role catalog.
Profiles can replace this provider while retaining the same Team mode, observable
casting facts, and plan-to-Team translation.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.application.casting import LLMTeamCaster
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import TEAM_CASTER, TEAM_CASTING_PROMPT_RENDERER
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.collaboration.casting import TeamCaster
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The standard LLM Team caster needs no plugin configuration."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-team-caster-default",
    provides=[TEAM_CASTER.key],
    requires=[TEAM_CASTING_PROMPT_RENDERER.key],
    implements=[TeamCaster],
    layer="L4",
    effects="none",
    description="Provide the default LLM-backed Team casting policy.",
    Config=Config,
    test_suite="tests/test_gateway_team_factory.py",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-team-caster-default.checked", "lca-team-caster-default.served")
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
    """Expose the caster with its profile-selected prompt content policy."""

    del config
    renderer = ctx.require(TEAM_CASTING_PROMPT_RENDERER.key)
    ctx.provide(TEAM_CASTER.key, LLMTeamCaster(renderer))


__all__ = ["Config", "setup"]
