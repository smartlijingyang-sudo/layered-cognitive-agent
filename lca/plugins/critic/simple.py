"""SimpleCritic plugin — named factory ``critic.simple``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Critic
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="lca-critic-simple",
    provides=["critic.simple"],
    implements=[Critic],
    layer="behavior",
    side_effects="none",
    policy_class="observe",
    description="Provide SimpleCritic as ``critic.simple``.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide SimpleCritic as ``critic.simple``."""
    from lca.layer1_cognitive.brain.critic import SimpleCritic

    ctx.provide("critic.simple", SimpleCritic)
