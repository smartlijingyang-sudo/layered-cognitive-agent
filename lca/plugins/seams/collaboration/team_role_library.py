"""Profile-selected RoleLibrary provider for automatic Team casting.

The default filesystem catalog is a replaceable Team input.  Keeping it in a
small provider means a profile can select an alternative role source without
changing the mode adapter or the Team casting translation.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.agent.role_library import FileRoleLibrary
from lca.contracts.capabilities import TEAM_ROLE_LIBRARY
from lca.contracts.protocols.collaboration.casting import RoleLibrary
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    """The repository role catalog needs no plugin configuration."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-team-role-library-default",
    provides=[TEAM_ROLE_LIBRARY.key],
    requires=[],
    implements=[RoleLibrary],
    layer="L3",
    effects="none",
    description="Provide the default filesystem-backed Team role library.",
    Config=Config,
    test_suite="tests/test_gateway_team_factory.py",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-team-role-library-default.checked', 'lca-team-role-library-default.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Expose the profile-selected role library to the Team mode adapter."""

    del config
    ctx.provide(TEAM_ROLE_LIBRARY.key, FileRoleLibrary())


__all__ = ["Config", "setup"]
