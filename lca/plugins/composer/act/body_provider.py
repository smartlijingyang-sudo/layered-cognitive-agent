"""Profile-visible provider for the plan-bound execution composer."""

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
from lca.plugins.composer.act.body_composer import BodyComposer


class Config(BaseModel):
    """Strict configuration for the built-in body composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-body-composer",
    provides=["composer.body"],
    requires=[],
    implements=["AgentGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound execution composer with a narrow act-cluster interface.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-plan-body-composer.checked", "lca-plan-body-composer.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("composer.body",),
        emits=("composer.body.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide only the profile-selected execution graph composer."""

    del config
    ctx.provide("composer.body", BodyComposer())


__all__ = ["Config", "setup"]
