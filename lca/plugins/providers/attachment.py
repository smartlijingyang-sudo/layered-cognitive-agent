"""Attachment Provider plugin — Tier-2."""
from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["filesystem"])


@plugin(name="lca-attachment-provider", inject=["attachment", "file_store"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer0_infra.attachment.service import FileStoreAttachmentIdentity

    if "filesystem" in config.providers:
        provider = FileStoreAttachmentIdentity(ctx.inject("file_store"))
        ctx.inject("attachment").register("filesystem", provider)
