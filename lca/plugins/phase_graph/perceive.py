"""标准 perceive PhaseExecutor。"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.act.command_envelope import RunDelta
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.phase_graph.capabilities import StandardPhaseCapabilities
from lca.plugins.phase_graph.common import (
    StandardPhaseConfig,
    fallback_phase_result,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.perceive.standard",
    phase=SemanticPhase.PERCEIVE,
    module="lca.plugins.phase_graph.perceive",
)


@dataclass(frozen=True, slots=True)
class StandardPerceiveExecutor:
    """Collect the profile-selected context manifest for the perceive node."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        hub = StandardPhaseCapabilities(context.capabilities).perceive_hub
        if hub is None:
            return fallback_phase_result(
                phase=SemanticPhase.PERCEIVE,
                result_kind="context",
                input=input,
            )
        manifest = await hub.perceive(context.state)
        return PhaseResult(
            result_kind="context",
            payload=manifest,
            deltas=(
                RunDelta(
                    plan_ref=context.plan_ref,
                    metadata={
                        "operation": "step",
                        "step": getattr(context.state, "step", -1) + 1,
                    },
                ),
                RunDelta(
                    plan_ref=context.plan_ref,
                    metadata={"operation": "perception", "manifest": manifest},
                ),
            ),
        )


@plugin(
    id="phase.perceive.standard",
    Config=StandardPhaseConfig,
    provides=("phase.perceive.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("phase_perceive_standard.checked", "phase_perceive_standard.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.perceive.standard", StandardPerceiveExecutor())


def create_executor() -> StandardPerceiveExecutor:
    return StandardPerceiveExecutor()


__all__ = ["StandardPerceiveExecutor", "create_executor"]
