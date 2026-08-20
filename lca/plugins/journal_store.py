"""Journal store plugin — named factory ``journal_store``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="lca-journal-store",
    provides=["journal_store"],
    layer="behavior",
    side_effects="none",
    policy_class="observe",
    description="Provide RunStore class as ``journal_store``; Composer instantiates per-run.",
    test_suite="tests/test_plugin_alignment.py::test_compose_root_no_inline_instantiation",
)
async def setup(ctx, config: Config) -> None:
    """Provide the RunStore class as ``journal_store``.

    Composer instantiates a RunStore per-run; this plugin only registers
    the class so composition can resolve it without importing layer0.
    """
    from lca.layer0_infra.observability import RunStore

    ctx.provide("journal_store", RunStore)
