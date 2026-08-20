"""SimpleCritic plugin — named factory ``critic.simple``."""

from __future__ import annotations
from pydantic import BaseModel
from lca.contracts.protocols import Critic
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-critic-simple",
    provides=["critic.simple"],
    implements=[Critic],
    layer="L1",
    effects="none",
    description="Provide SimpleCritic as ``critic.simple``.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    """Provide SimpleCritic as ``critic.simple``."""
    from lca.layer1_cognitive.brain.critic import SimpleCritic

    ctx.provide("critic.simple", SimpleCritic)
