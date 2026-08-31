"""标准 remember PhaseExecutor。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.protocols.act.command_envelope import CapabilityGrant, RunDelta, mint_envelope
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.plugins.phase_graph.capabilities import StandardPhaseCapabilities
from lca.plugins.phase_graph.common import (
    StandardPhaseConfig,
    fallback_phase_result,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.remember.standard",
    phase=SemanticPhase.REMEMBER,
    module="lca.plugins.phase_graph.remember",
    effects=("memory",),
)


@dataclass(frozen=True, slots=True)
class StandardRememberExecutor:
    """Commit the act and reflection artifacts through the memory effect seam."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        memory = StandardPhaseCapabilities(context.capabilities).memory
        decision = cast("Decision | None", context.artifacts.get("think"))
        observation = cast("Observation | None", context.artifacts.get("act"))
        reflection = cast("Reflection | None", context.artifacts.get("reflect"))
        if memory is None or decision is None or observation is None or reflection is None:
            return fallback_phase_result(
                phase=SemanticPhase.REMEMBER,
                result_kind="write_set",
                input=input,
            )
        envelope = mint_envelope(
            plan_ref=context.plan_ref,
            scope_ref=context.node_ref,
            decision=decision,
            provider="effect.memory",
            grant=CapabilityGrant(capability="memory.update", scope="run", effect_class="memory"),
            idempotency_key=f"{context.plan_ref}:{context.node_ref}:{decision.decision_id}",
            metadata={
                "effect_class": "memory",
                "operation": "memory.update",
                "state": context.state,
                "observation": observation,
                "reflection": reflection,
            },
        )
        return PhaseResult(
            result_kind="write_set",
            payload={"admitted": True},
            command_envelope=envelope,
            deltas=(
                RunDelta(
                    plan_ref=context.plan_ref,
                    metadata={
                        "operation": "turn",
                        "decision": decision,
                        "observation": observation,
                        "reflection": reflection,
                    },
                ),
                RunDelta(plan_ref=context.plan_ref, metadata={"operation": "memory"}),
            ),
        )


@plugin(
    id="phase.remember.standard",
    Config=StandardPhaseConfig,
    provides=("phase.remember.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_phase_graph.py",
    spec=SPEC,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('phase_remember_standard.checked', 'phase_remember_standard.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase.remember.standard", StandardRememberExecutor())


def create_executor() -> StandardRememberExecutor:
    return StandardRememberExecutor()


__all__ = ["StandardRememberExecutor", "create_executor"]
