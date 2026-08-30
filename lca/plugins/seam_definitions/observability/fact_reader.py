"""Fact reader seam plugin (Tier-1).

声明 ``fact_readers`` 注册中心；boot 后 ``providers/fact_reader`` 把各种
``JournalProjector`` factory 注入。新增 fact reader = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import JournalProjector
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-fact-reader-seam",
    provides=["fact_readers"],
    implements=[JournalProjector],
    layer="L0",
    effects="none",
    description="Provide the fact_readers seam (facade plugin-ification).",
    test_suite="tests/test_fact_reader_plugin.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry

    ctx.provide("fact_readers", NamedRegistry())
