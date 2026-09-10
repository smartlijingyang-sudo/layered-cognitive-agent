"""phase.think.local_gate — enforce Decision via the per-think local DecisionGate.

Part of PR-2 think subgraph decompress (Task 2). Extracted from the
legacy ``phase.think.gate`` step: local_gate owns the per-think local
enforce; plan-bound enforcement lives in the separate
``phase.think.agent_gate`` step (Task 3); the terminal sink that turns
the enforced decision into a typed ``verdict.v1`` fact lives in
``phase.think.verdict_emit`` (Task 4).

Behavior contract:
- Reads capability key ``phase.think.local_gate`` (a ``DecisionGate``).
- If the capability is absent, the carry is passed through unchanged
  with ``result_kind="think_stage"`` — missing local gate is not an
  error (mirrors the legacy contract; absence means "no local rule").
- If the candidate ``carry.decision`` is ``None``, returns the input
  artifact as a terminal fallback (``result_kind="decision"``) — matches
  the legacy phase_graph contract when no decision ever materialised.
- Otherwise enforces and returns ``result_kind="think_stage"`` with the
  updated carry as payload; the runner hands it to the next step.

The step never reads ``phase.think.agent_gates`` — splitting local vs
plan-bound enforcement is the whole point of this task.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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
from lca.contracts.plugins.think.step_plugin_spec import step_plugin_spec
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

STAGE_KIND = "think_stage"
TERMINAL_KIND = "decision"

SPEC = step_plugin_spec(
    plugin_id="phase.think.local_gate",
    module="lca.plugins.think.local_gate.plugin",
    test_suite="tests/think/test_local_gate_phase_plugin.py",
)


def _carry(context: PhaseContext) -> ThinkSubgraphCarry:
    existing = context.artifacts.get(CARRY_KEY)
    if isinstance(existing, ThinkSubgraphCarry):
        return existing
    return ThinkSubgraphCarry(state=context.state)


@dataclass(frozen=True, slots=True)
class ThinkLocalGateExecutor:
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        carry = _carry(context)
        if carry.decision is None:
            return PhaseResult(result_kind=TERMINAL_KIND, payload=input.artifact)
        gate = context.capabilities.get("phase.think.local_gate")
        if not isinstance(gate, DecisionGate):
            return PhaseResult(result_kind=STAGE_KIND, payload=carry)
        enforced = await gate.enforce(carry.state, carry.decision)
        return PhaseResult(
            result_kind=STAGE_KIND,
            payload=replace(carry, decision=enforced),
        )


@plugin(
    id="phase.think.local_gate",
    Config=StandardPhaseConfig,
    provides=("phase.think.local_gate",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/think/test_local_gate_phase_plugin.py",
    spec=SPEC,
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
                "phase_think_local_gate.checked",
                "phase_think_local_gate.served",
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
    ctx.provide("phase.think.local_gate", ThinkLocalGateExecutor())


def create_executor() -> ThinkLocalGateExecutor:
    return ThinkLocalGateExecutor()


__all__ = ["ThinkLocalGateExecutor", "create_executor", "setup"]
