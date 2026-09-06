"""Profile-visible provider for the plan-bound perceive composer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.composer.perceive.perceive_composer import PerceiveComposer


class Config(BaseModel):
    """Strict configuration for the built-in perceive composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-perceive-composer",
    provides=["composer.perceive"],
    requires=[],
    implements=["AgentGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound perceive composer with a narrow context-and-state interface.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("context.read",)),
        observability=EvidenceContract(
            descriptors=("lca-plan-perceive-composer.checked", "lca-plan-perceive-composer.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("composer.perceive",),
        emits=("composer.perceive.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide only the profile-selected perceive graph composer."""

    del config
    ctx.provide("composer.perceive", PerceiveComposer())


__all__ = ["Config", "setup"]
