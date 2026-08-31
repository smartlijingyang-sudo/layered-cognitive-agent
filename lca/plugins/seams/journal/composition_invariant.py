"""Profile-selected invariant checker for governed Cordis composition."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.capabilities import COMPOSITION_INVARIANT_CHECKER
from lca.contracts.mechanisms.composition import InvariantChecker
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.plugins.providers.think.composition_composer import build_default_invariant_checker


class Config(BaseModel):
    """The standard invariant checker has no profile parameters."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-composition-invariant-default",
    provides=[COMPOSITION_INVARIANT_CHECKER.key],
    requires=[],
    implements=[InvariantChecker],
    layer="L0",
    effects="none",
    description="Provide the default invariant gate for Cordis Composer mount operations.",
    test_suite="tests/architecture/test_composition_invariant_capability.py",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-composition-invariant-default.checked', 'lca-composition-invariant-default.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the profile-selected composition invariant checker."""

    del config
    ctx.provide(COMPOSITION_INVARIANT_CHECKER.key, build_default_invariant_checker())


__all__ = ["Config", "setup"]
