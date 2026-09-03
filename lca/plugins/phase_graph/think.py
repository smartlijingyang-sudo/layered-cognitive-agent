"""标准 think PhaseExecutor。"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.phase_graph.capabilities import StandardPhaseCapabilities
from lca.plugins.phase_graph.common import (
    StandardPhaseConfig,
    fallback_phase_result,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.think.standard",
    phase=SemanticPhase.THINK,
    module="lca.plugins.phase_graph.think",
)


@dataclass(frozen=True, slots=True)
class StandardThinkExecutor:
    """Create a decision through the profile-selected Brain capability."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        brain = StandardPhaseCapabilities(context.capabilities).brain
        if brain is None:
            return fallback_phase_result(
                phase=SemanticPhase.THINK,
                result_kind="decision",
                input=input,
            )
        return PhaseResult(result_kind="decision", payload=await brain.think(context.state))


@plugin(
    id="phase.think.standard",
    Config=StandardPhaseConfig,
    provides=("phase.think.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_think_standard.checked", "phase_think_standard.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.think.standard", StandardThinkExecutor())


def create_executor() -> StandardThinkExecutor:
    return StandardThinkExecutor()


__all__ = ["StandardThinkExecutor", "create_executor"]
