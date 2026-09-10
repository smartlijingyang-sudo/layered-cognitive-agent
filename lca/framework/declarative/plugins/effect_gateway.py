"""Default ``effect_gateway`` capability provider.

Provides a null effect dispatcher so the interpreter plugin can be wired
even when a profile has not yet contributed a registry-backed dispatcher.
A production profile must override this capability before any phase that
emits world-affecting commands.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    EffectDispatcher,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The default null effect gateway has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


class NullEffectDispatcher(EffectDispatcher):
    """Reject every effect execution; explicit fail-closed null default."""

    async def execute(self, envelope: object, policy: object) -> object:
        del envelope, policy
        raise NotImplementedError(
            "NullEffectDispatcher rejected effect; install a registry-backed "
            "EffectDispatcher provider before phases may execute world effects."
        )


@plugin(
    id="declarative.effect_gateway",
    requires=[],
    provides=["effect_gateway"],
    implements=[EffectDispatcher],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default null EffectDispatcher so declarative profiles have "
        "a fail-closed gateway until a registry-backed provider replaces it."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "declarative.effect_gateway.checked",
                "declarative.effect_gateway.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("effect_gateway",),
        emits=("effect_gateway.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default null EffectDispatcher to runtime assembly."""

    del config
    ctx.provide("effect_gateway", NullEffectDispatcher())


__all__ = ["Config", "NullEffectDispatcher", "setup"]
