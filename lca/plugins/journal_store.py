"""Journal store plugin — named factory ``journal_store``."""

from __future__ import annotations
from pydantic import BaseModel
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-journal-store",
    provides=["journal_store"],
    layer="L1",
    effects="none",
    description="Provide RunStore class as ``journal_store``; Composer instantiates per-run.",
    test_suite="tests/test_plugin_alignment.py::test_compose_root_no_inline_instantiation",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    """Provide the RunStore class as ``journal_store``.

    Composer instantiates a RunStore per-run; this plugin only registers
    the class so composition can resolve it without importing layer0.
    """
    from lca.layer0_infra.observability import RunStore

    ctx.provide("journal_store", RunStore)
