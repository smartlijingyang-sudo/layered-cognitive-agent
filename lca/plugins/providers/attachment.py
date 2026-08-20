"""Attachment Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.infra import AttachmentIdentity
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


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
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.attachment.service import FileStoreAttachmentIdentity

    if "filesystem" in config.providers:
        provider = FileStoreAttachmentIdentity(ctx.inject("file_store"))
        ctx.inject("attachment").register("filesystem", provider)
