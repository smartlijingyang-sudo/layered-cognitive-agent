"""File Store Provider plugin — Tier-2."""

from __future__ import annotations

from pathlib import Path

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
    local_root: Path = Path("traces/files")
    public_url_prefix: str = "/files"


@plugin(
    id="lca-file-store-provider",
    requires=["file_store"],
    layer="L0",
    effects="world",
    description="Register FileStore providers on the FileStoreService Definition.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PROVIDER,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-file-store-provider.checked", "lca-file-store-provider.served"),
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
    from lca.infrastructure.file_store import LocalFileStore

    service = ctx.require("file_store")
    if "local" in config.providers and not service.providers.names():
        service.register(
            "local",
            LocalFileStore(config.local_root, public_url_prefix=config.public_url_prefix),
        )
