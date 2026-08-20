"""JournalStore factory plugin (Tier-2) —— ADR-0063 PR-8.

把 ``InMemoryJournalStore`` 注册为 ``journal_store_factories`` 的 factory。
后续 PR-8-ext 可加 ``journal_store_factories.file`` factory，无需改 seam。
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.observability.journal_store import JournalStoreBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default: str = Field(default="memory", description="默认 backend 名称")


@plugin(
    id="lca-journal-store-memory-factory",
    requires=["journal_store_factories"],
    implements=None,  # type: ignore[arg-type]
    layer="L0",
    effects="none",
    description="Register JournalStoreBackend factories (PR-8).",
    test_suite="tests/test_journal_store_backend.py::test_provider_registers_memory_factory",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import InMemoryJournalStore, NamedRegistry

    def _make_memory() -> JournalStoreBackend:
        return InMemoryJournalStore()

    registry: NamedRegistry = ctx.require("journal_store_factories")
    registry.register("memory", _make_memory)