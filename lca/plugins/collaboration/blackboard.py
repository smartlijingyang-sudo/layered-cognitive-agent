"""InMemoryBlackboard plugin — named factory ``blackboard.in-memory``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.collaboration.blackboard import InMemoryBlackboard


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="lca-blackboard-memory")
async def setup(ctx: Context, config: Config) -> None:
    """Provide InMemoryBlackboard as ``blackboard.in-memory``."""
    ctx.provide("blackboard.in-memory", InMemoryBlackboard)
