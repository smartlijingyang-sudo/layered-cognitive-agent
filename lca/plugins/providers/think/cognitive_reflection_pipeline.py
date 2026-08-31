"""Default provider for the composable Reflect cognitive primitive."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import COGNITIVE_REFLECTION_PIPELINE
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.think.cognitive_pipeline import CognitiveReflectionPipeline
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Strict empty configuration for the standard stateless pipeline."""

    model_config = {"extra": "forbid"}


@plugin(  # type: ignore[arg-type]  # PluginContext currently erases Config covariance.
    id="lca-cognitive-reflection-pipeline-standard",
    provides=[COGNITIVE_REFLECTION_PIPELINE.key],
    requires=[],
    implements=[CognitiveReflectionPipeline],
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    functional_group=FunctionalGroup.G5_COGNITION,
    description=(
        "Provide the standard Reflect primitive pipeline; profiles may replace its "
        "critic/fallback semantics without replacing the Brain or Agent Loop."
    ),
    test_suite="tests/test_cognitive_pipeline_plugins.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-cognitive-reflection-pipeline-standard.checked",
                "lca-cognitive-reflection-pipeline-standard.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Bind the standard, stateless Reflect pipeline to the capability graph."""

    del config
    from lca.cognition.brain.cognitive_pipeline import (
        StandardCognitiveReflectionPipeline,
    )

    ctx.provide(
        COGNITIVE_REFLECTION_PIPELINE.key,
        StandardCognitiveReflectionPipeline(),
    )


__all__ = ["COGNITIVE_REFLECTION_PIPELINE", "Config", "setup"]
