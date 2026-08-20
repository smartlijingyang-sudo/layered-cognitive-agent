"""ArtifactRespondInjector plugin — named factory ``gate.artifact-respond-injector``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="gate.artifact-respond-injector",
    provides=["gate.artifact-respond-injector"],
    implements=[DecisionGate],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="Inject artifact references into terminal respond actions.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named gate factory ``gate.artifact-respond-injector``."""
    from lca.layer1_cognitive.brain.decision_gates.artifact_respond_injector import (
        ArtifactRespondInjector,
    )

    ctx.provide("gate.artifact-respond-injector", ArtifactRespondInjector)
