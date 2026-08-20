"""SimpleCritic plugin — named factory ``critic.simple``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.critic import SimpleCritic


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="lca-critic-simple")
async def setup(ctx: Context, config: Config) -> None:
    """Provide SimpleCritic as ``critic.simple``."""
    ctx.provide("critic.simple", SimpleCritic)
