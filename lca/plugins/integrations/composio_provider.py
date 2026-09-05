"""Composio Provider plugin — binds Profile config to ComposioIntegration."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr

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
    api_key: SecretStr | str = Field(min_length=1)
    base_url: str | None = None
    callback_url: str | None = None
    default_user_id: str | None = None
    auth_config_ids: str | dict[str, str] | None = None
    connections_path: str | None = None


def _secret_value(value: SecretStr | str) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


@plugin(
    id="lca-composio-provider",
    provides=["composio"],
    layer="L0",
    effects="tools",
    description="Configure ComposioIntegration from Profile-injected credentials.",
    test_suite="tests/test_composio_integration.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-composio-provider.checked", "lca-composio-provider.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.integrations.composio.service import ComposioIntegration
    from lca.infrastructure.integrations.composio.settings import ComposioSettings

    api_key = _secret_value(config.api_key).strip()
    if not api_key:
        raise RuntimeError("lca-composio-provider: api_key is required")

    settings = ComposioSettings.from_plugin_config(
        api_key=api_key,
        base_url=config.base_url,
        callback_url=config.callback_url,
        default_user_id=config.default_user_id,
        auth_config_ids=config.auth_config_ids,
        connections_path=config.connections_path,
    )
    ctx.provide("composio", ComposioIntegration(settings))
