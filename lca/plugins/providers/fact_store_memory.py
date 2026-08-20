"""Fact store memory factory plugin (Tier-2) —— ADR-0063 PR-8.

把 ``InMemoryJournalStore`` 注册为 ``journal_store_factories`` 的 factory。
文件 backed / 远端实现由后续 PR 的 Plugin 落地，不改 seam。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.observability.journal_store import JournalStoreBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-fact-store-memory-factory",
    requires=["journal_store_factories"],
    implements=[JournalStoreBackend],
    layer="L0",
    effects="memory",
    description="Register InMemoryJournalStore factory as journal_store_factories['memory'].",
    test_suite="tests/test_journal_store_backend.py::test_provider_registers_memory_factory",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import InMemoryJournalStore, NamedRegistry

    registry: NamedRegistry = ctx.require("journal_store_factories")

    def _make_memory(settings: Any = None, **_: Any) -> JournalStoreBackend:
        _ = settings
        return InMemoryJournalStore()

    registry.register("memory", _make_memory)
