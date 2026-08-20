"""ConcatSynthesizer plugin — named factory ``synthesizer.concat``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Synthesizer
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="lca-synthesizer-concat",
    provides=["synthesizer.concat"],
    implements=[Synthesizer],
    layer="behavior",
    side_effects="none",
    policy_class="observe",
    description="Provide ConcatSynthesizer as ``synthesizer.concat``.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide ConcatSynthesizer as ``synthesizer.concat``."""
    from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer

    ctx.provide("synthesizer.concat", ConcatSynthesizer)
