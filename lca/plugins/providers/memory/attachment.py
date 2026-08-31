"""Attachment Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.runtime.infra import AttachmentIdentity
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["filesystem"])


@plugin(
    id="lca-attachment-provider",
    requires=["attachment", "file_store"],
    implements=[AttachmentIdentity],
    layer="L0",
    effects="world",
    description="Register AttachmentIdentity providers on the AttachmentService Definition.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-attachment-provider.checked', 'lca-attachment-provider.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.attachment.service import FileStoreAttachmentIdentity

    if "filesystem" in config.providers:
        provider = FileStoreAttachmentIdentity(ctx.require("file_store"))
        ctx.require("attachment").register("filesystem", provider)
