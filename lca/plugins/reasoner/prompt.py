"""PromptReasoner plugin — named factory ``reasoner.prompt``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Reasoner
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="lca-reasoner-prompt",
    provides=["reasoner.prompt"],
    implements=[Reasoner],
    layer="behavior",
    side_effects="none",
    policy_class="control",
    description="Provide the PromptReasoner class as ``reasoner.prompt``.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the PromptReasoner class as ``reasoner.prompt``.

    ModularBrain still constructs Reasoner internally; this key lets a
    Composer or an alternate Brain factory resolve the Standard reasoner
    without importing layer1.
    """
    from lca.layer1_cognitive.brain.reasoner import PromptReasoner

    ctx.provide("reasoner.prompt", PromptReasoner)
