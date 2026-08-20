"""ArtifactRespondInjector contribution — posts onto GateService."""

from __future__ import annotations
from pydantic import BaseModel
from lca.contracts.protocols import DecisionGate
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gate.artifact-respond-injector",
    requires=["gates"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Inject artifact references into terminal respond actions.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.artifact_respond_injector import (
        ArtifactRespondInjector,
    )

    ctx.inject("gates").add(
        ArtifactRespondInjector, id="artifact-respond-injector", slot="loop", order=50
    )
