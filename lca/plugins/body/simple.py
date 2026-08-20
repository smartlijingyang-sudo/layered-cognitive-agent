"""SimpleBody plugin — named factory ``body.simple``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.body.simple_body import SimpleBody


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="body.simple")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named Body factory ``body.simple``."""
    ctx.provide("body.simple", SimpleBody)
