"""标准 act PhaseExecutor。"""

from __future__ import annotations

from lca.contracts.models.core.execution.decision import Decision

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.act.command.envelope import CapabilityGrant, mint_envelope
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.capabilities import StandardPhaseCapabilities
from lca.plugins.loop.phase._shared.common import (
    StandardPhaseConfig,
    fallback_phase_result,
    standard_phase_spec,
)

SPEC = standard_phase_spec(
    plugin_id="phase.act.standard",
    phase=SemanticPhase.ACT,
    module="lca.plugins.loop.phase.act.standard.plugin",
    effects=("tools",),
)


@dataclass(frozen=True, slots=True)
class StandardActExecutor:
    """Authorize the selected Body operation through the effect gateway."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        # ADR-0219 §4.3: typed read.
        body = StandardPhaseCapabilities(context.capabilities).body
        decision = context.payload_of(SemanticPhase.THINK, Decision)
        if body is None or decision is None:
            return fallback_phase_result(
                phase=SemanticPhase.ACT,
                result_kind="observation",
                input=input,
            )
        envelope = mint_envelope(
            plan_ref=context.plan_ref,
            scope_ref=context.node_ref,
            decision=decision,
            provider="effect.body",
            grant=CapabilityGrant(capability="body.act", scope="run", effect_class="tools"),
            idempotency_key=f"{context.plan_ref}:{context.node_ref}:{decision.decision_id}",
            metadata={
                "effect_class": "tools",
                "operation": "body.act",
                "state": context.state,
                "decision": decision,
            },
        )
        return PhaseResult(result_kind="observation", command_envelope=envelope)


@plugin(
    id="phase.act.standard",
    Config=StandardPhaseConfig,
    provides=("phase.act.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="tools",
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
            descriptors=("phase_act_standard.checked", "phase_act_standard.served")
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
    ctx.provide("phase.act.standard", StandardActExecutor())


def create_executor() -> StandardActExecutor:
    return StandardActExecutor()


__all__ = ["StandardActExecutor", "create_executor"]
