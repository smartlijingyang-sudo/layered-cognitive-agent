"""NullCritic plugin — named factory ``critic.null`` (ADR-0068 / 宪法 §3.4)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Critic
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-critic-null",
    provides=["critic.null"],
    implements=[Critic],
    layer="L1",
    effects="none",
    description="Provide NullCritic as ``critic.null`` (ADR-0068 default).",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide NullCritic as ``critic.null``."""
    from lca.layer1_cognitive.brain.null_critic import NullCritic

    ctx.provide("critic.null", NullCritic)
