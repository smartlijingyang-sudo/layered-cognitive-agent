"""ConcatSynthesizer plugin — named factory ``synthesizer.concat``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Synthesizer
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-synthesizer-concat",
    provides=["synthesizer.concat"],
    implements=[Synthesizer],
    layer="L1",
    effects="none",
    description="Provide ConcatSynthesizer as ``synthesizer.concat``.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide ConcatSynthesizer as ``synthesizer.concat``."""
    from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer

    ctx.provide("synthesizer.concat", ConcatSynthesizer)
