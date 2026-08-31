"""Profile-visible provider for the plan-bound cognitive composer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.plugins.composer.think.brain_composer import BrainComposer


class Config(BaseModel):
    """Strict configuration for the built-in brain composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-brain-composer",
    provides=["composer.brain"],
    requires=[],
    implements=["AgentGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound cognitive composer with a narrow think-cluster interface.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-plan-brain-composer.checked', 'lca-plan-brain-composer.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide only the profile-selected cognitive graph composer."""

    del config
    ctx.provide("composer.brain", BrainComposer())


__all__ = ["Config", "setup"]
