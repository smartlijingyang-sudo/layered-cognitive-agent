"""InMemoryBlackboard plugin — named factory ``blackboard.in-memory``."""

from __future__ import annotations
from pydantic import BaseModel
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-blackboard-memory",
    provides=["blackboard.in-memory"],
    layer="L1",
    effects="none",
    description="Provide InMemoryBlackboard as ``blackboard.in-memory``.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    """Provide InMemoryBlackboard as ``blackboard.in-memory``."""
    from lca.layer1_cognitive.collaboration.blackboard import InMemoryBlackboard

    ctx.provide("blackboard.in-memory", InMemoryBlackboard)
