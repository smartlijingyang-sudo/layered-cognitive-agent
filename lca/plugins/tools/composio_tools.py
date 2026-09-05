"""Composio tools factory — registers connect/refresh + dynamic Composio actions."""

from __future__ import annotations

from pydantic import BaseModel

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
from lca.contracts.protocols.runtime.infra import Tool
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    enabled: bool = True


@plugin(
    id="lca-composio-tools",
    requires=["composio", "tools"],
    implements=[Tool],
    layer="L1",
    effects="tools",
    description="Register Composio tool factory on the ToolsService Definition.",
    test_suite="tests/test_composio_integration.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve", "tool.invoke")),
        observability=EvidenceContract(
            descriptors=("lca-composio-tools.checked", "lca-composio-tools.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "composio"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    if not config.enabled:
        return

    integration = ctx.require("composio")

    def _factory(run: object | None = None) -> list[Tool]:
        from lca.infrastructure.tools.composio import build_tools

        return build_tools(integration)

    ctx.require("tools").register_factory("composio", _factory)
