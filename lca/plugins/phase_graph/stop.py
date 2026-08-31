"""标准 stop PhaseExecutor。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

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
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.act.command_envelope import RunDelta
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseContext,
    PhaseExecutionFailure,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.phase_graph.capabilities import StandardPhaseCapabilities
from lca.plugins.phase_graph.common import StandardPhaseConfig, standard_phase_spec
from lca.plugins.phase_graph.failure_stop import phase_failure_stop_result

SPEC = standard_phase_spec(
    plugin_id="phase.stop.standard",
    phase=SemanticPhase.STOP,
    module="lca.plugins.phase_graph.stop",
)


@dataclass(frozen=True, slots=True)
class StandardStopExecutor:
    """Apply failure termination or consult the stop phase's local StopPolicy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        failure = input.artifact
        if isinstance(failure, PhaseExecutionFailure):
            return phase_failure_stop_result(failure, plan_ref=context.plan_ref)
        stop_policy = StandardPhaseCapabilities(context.capabilities).stop_policy
        if stop_policy is None:
            return PhaseResult(
                result_kind="stop_decision",
                payload=StopDecision(
                    should_stop=True,
                    reason=StopReason.TASK_COMPLETED,
                ),
            )
        stop = stop_policy.decide(
            context.state,
            cast("Decision | None", context.artifacts.get("think")),
            cast("Observation | None", context.artifacts.get("act")),
            cast("Reflection | None", context.artifacts.get("reflect")),
        )
        return PhaseResult(
            result_kind="stop_decision",
            payload=stop,
            deltas=(
                RunDelta(plan_ref=context.plan_ref, metadata={"operation": "stop", "stop": stop}),
            ),
        )


@plugin(
    id="phase.stop.standard",
    Config=StandardPhaseConfig,
    provides=("phase.stop.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
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
            descriptors=("phase_stop_standard.checked", "phase_stop_standard.served")
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
    ctx.provide("phase.stop.standard", StandardStopExecutor())


def create_executor() -> StandardStopExecutor:
    return StandardStopExecutor()


__all__ = ["StandardStopExecutor", "create_executor"]
