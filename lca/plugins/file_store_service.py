"""File store Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-file-store-service")
async def setup(ctx: Context, config: Any) -> None:
    from lca.layer0_infra.capability.files import FileStoreService

    service = FileStoreService()
    ctx.provide("file_store", service)
