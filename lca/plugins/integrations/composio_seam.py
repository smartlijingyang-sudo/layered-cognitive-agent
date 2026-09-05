"""Composio Service Definition plugin — Tier-1."""

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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-composio-service",
    provides=["composio"],
    layer="L0",
    effects="tools",
    description="Provide the Composio integration Definition (connection + execute).",
    test_suite="tests/test_composio_integration.py",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-composio-service.checked", "lca-composio-service.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("composio",),
        emits=("composio.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.integrations.composio.service import ComposioIntegration
    from lca.infrastructure.integrations.composio.settings import ComposioSettings

    # Provider replaces this placeholder with a configured instance.
    ctx.provide("composio", ComposioIntegration(ComposioSettings.from_plugin_config(api_key="")))
