"""NullSynthesizer plugin — named factory ``synthesizer.null`` (ADR-0068 / 宪法 §3.4)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Synthesizer
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-synthesizer-null",
    provides=["synthesizer.null"],
    implements=[Synthesizer],
    layer="L1",
    effects="none",
    description="Provide NullSynthesizer as ``synthesizer.null`` (ADR-0068 default).",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide NullSynthesizer as ``synthesizer.null``."""
    from lca.cognition.brain.null_synthesizer import NullSynthesizer

    ctx.provide("synthesizer.null", NullSynthesizer)
