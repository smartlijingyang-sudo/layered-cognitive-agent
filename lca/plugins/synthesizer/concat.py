"""ConcatSynthesizer plugin — named factory ``synthesizer.concat``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="lca-synthesizer-concat")
async def setup(ctx: Context, config: Config) -> None:
    """Provide ConcatSynthesizer as ``synthesizer.concat``."""
    ctx.provide("synthesizer.concat", ConcatSynthesizer)
