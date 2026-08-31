"""Profile-visible provider for the plan-bound execution composer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
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


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-plan-body-composer.checked', 'lca-plan-body-composer.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide only the profile-selected execution graph composer."""

    del config
    ctx.provide("composer.body", BodyComposer())


__all__ = ["Config", "setup"]
