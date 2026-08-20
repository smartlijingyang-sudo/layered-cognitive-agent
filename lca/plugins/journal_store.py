"""Journal store plugin — named factory ``journal_store``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer0_infra.observability import RunStore


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="lca-journal-store")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the RunStore class as ``journal_store``.

    Composer instantiates a RunStore per-run; this plugin only registers
    the class so composition can resolve it without importing layer0.
    """
    ctx.provide("journal_store", RunStore)
