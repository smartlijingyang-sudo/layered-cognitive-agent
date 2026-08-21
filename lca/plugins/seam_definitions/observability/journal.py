"""Journal seam plugin (Tier-1).

声明 ``journal_backends`` 注册中心；boot 后 ``providers/journal_memory`` 把
``MemoryJournal`` factory 注入。新增 journal backend = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.ports import JournalBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-journal-seam",
    provides=["journal_backends"],
    implements=[JournalBackend],
    layer="L0",
    effects="none",
    description="Provide the journal_backends seam (facade plugin-ification).",
    test_suite="tests/test_journal_plugin.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry

    ctx.provide("journal_backends", NamedRegistry())
