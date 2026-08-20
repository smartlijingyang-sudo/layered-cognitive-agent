"""ArtifactRespondInjector plugin — named factory ``gate.artifact-respond-injector``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.layer1_cognitive.brain.decision_gates.artifact_respond_injector import (
    ArtifactRespondInjector,
)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(name="gate.artifact-respond-injector")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named gate factory ``gate.artifact-respond-injector``."""
    ctx.provide("gate.artifact-respond-injector", ArtifactRespondInjector)
