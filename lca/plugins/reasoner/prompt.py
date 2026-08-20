"""PromptReasoner plugin — named factory ``reasoner.prompt``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.reasoner import PromptReasoner


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="lca-reasoner-prompt")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the PromptReasoner class as ``reasoner.prompt``.

    ModularBrain still constructs Reasoner internally; this key lets a
    Composer or an alternate Brain factory resolve the Standard reasoner
    without importing layer1.
    """
    ctx.provide("reasoner.prompt", PromptReasoner)
