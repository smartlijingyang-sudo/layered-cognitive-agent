"""phase.think.gate — enforce Decision via DecisionGate and optional agent gates."""

from __future__ import annotations

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
from lca.contracts.models.core.execution.think_carry import CARRY_KEY, ThinkSubgraphCarry
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseContext,
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.common import StandardPhaseConfig


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkGateExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        carry = _carry(context)
        if carry.decision is None:
            # No candidate decision — treat as terminal fallback with the
            # input artifact (which preserves prior phase_graph contract).
            return PhaseResult(result_kind="decision", payload=input.artifact)
        decision = carry.decision
        gate = context.capabilities.get("phase.think.gate")
        if isinstance(gate, DecisionGate):
            decision = await gate.enforce(carry.state, decision)
        agent_gates = context.capabilities.get("phase.think.agent_gates")
        if isinstance(agent_gates, DecisionGate):
            decision = await agent_gates.enforce(carry.state, decision)
        return PhaseResult(result_kind="decision", payload=decision)


@plugin(
    id="phase.think.gate",
    Config=StandardPhaseConfig,
    provides=("phase.think.gate",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_gate_phase_plugin.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_gate.checked",
                "phase_think_gate.served",
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
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    del config
    ctx.provide("phase.think.gate", ThinkGateExecutor())


def create_executor() -> ThinkGateExecutor:
    return ThinkGateExecutor()


__all__ = ["ThinkGateExecutor", "create_executor", "setup"]
