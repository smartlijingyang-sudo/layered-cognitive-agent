"""Workspace Provider plugin — Tier-2 (placeholder).

Full WorkspaceService does not yet exist in lca/infrastructure/workspace/.
This Tier-2 stub is a safe default that registers a no-op workspace.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(
    id="lca-workspace-provider",
    requires=["workspace"],
    layer="L0",
    effects="none",
    description="Placeholder Workspace provider — real implementation deferred.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PROVIDER,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-workspace-provider.checked", "lca-workspace-provider.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """WorkspaceService does not exist yet; deferred to follow-up."""
    pass
