"""InMemoryBlackboard plugin — named factory ``blackboard.in-memory``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="lca-blackboard-memory",
    provides=["blackboard.in-memory"],
    layer="behavior",
    side_effects="none",
    policy_class="observe",
    description="Provide InMemoryBlackboard as ``blackboard.in-memory``.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide InMemoryBlackboard as ``blackboard.in-memory``."""
    from lca.layer1_cognitive.collaboration.blackboard import InMemoryBlackboard

    ctx.provide("blackboard.in-memory", InMemoryBlackboard)
