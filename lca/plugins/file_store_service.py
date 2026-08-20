"""File store Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-file-store-service",
    provides=["file_store"],
    implements=[],
    layer="service",
    side_effects="world",
    policy_class="control",
    description="Provide the FileStore Definition service (ProviderDispatch + file-store table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.files import FileStoreService

    service = FileStoreService()
    ctx.provide("file_store", service)
