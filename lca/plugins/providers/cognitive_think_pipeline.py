"""Default provider for the composable Think cognitive primitive."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.capabilities import COGNITIVE_THINK_PIPELINE
from lca.contracts.protocols.cognitive_pipeline import CognitiveThinkPipeline
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Strict empty configuration for the standard stateless pipeline."""

    model_config = {"extra": "forbid"}


@plugin(  # type: ignore[arg-type]  # PluginContext currently erases Config covariance.
    id="lca-cognitive-think-pipeline-standard",
    provides=[COGNITIVE_THINK_PIPELINE.key],
    requires=[],
    implements=[CognitiveThinkPipeline],
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    functional_group=FunctionalGroup.G5_COGNITION,
    description=(
        "Provide the standard Think primitive pipeline; profiles may replace only this "
        "subflow without replacing the Brain or Agent Loop."
    ),
    test_suite="tests/test_cognitive_pipeline_plugins.py",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Bind the standard, stateless Think pipeline to the capability graph."""

    del config
    from lca.layer1_cognitive.brain.cognitive_pipeline import StandardCognitiveThinkPipeline

    ctx.provide(COGNITIVE_THINK_PIPELINE.key, StandardCognitiveThinkPipeline())


__all__ = ["COGNITIVE_THINK_PIPELINE", "Config", "setup"]
