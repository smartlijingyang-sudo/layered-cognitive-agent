"""PromptReasoner plugin — named factory ``reasoner.prompt``."""

from __future__ import annotations
from pydantic import BaseModel
from lca.contracts.protocols import Reasoner
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-reasoner-prompt",
    provides=["reasoner.prompt"],
    implements=[Reasoner],
    layer="L1",
    effects="none",
    description="Provide the PromptReasoner class as ``reasoner.prompt``.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    """Provide the PromptReasoner class as ``reasoner.prompt``.

    ModularBrain still constructs Reasoner internally; this key lets a
    Composer or an alternate Brain factory resolve the Standard reasoner
    without importing layer1.
    """
    from lca.layer1_cognitive.brain.reasoner import PromptReasoner

    ctx.provide("reasoner.prompt", PromptReasoner)
