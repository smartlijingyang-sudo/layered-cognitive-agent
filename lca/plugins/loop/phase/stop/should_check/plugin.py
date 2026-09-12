"""phase.stop.should_check — primitive: invoke StopPolicy, emit typed decision.

ADR-0221: reads typed ``decision`` / ``observation`` / ``reflection``
ports from upstream phases and consults the profile-selected
``stop_policy`` capability (via runtime) to emit a typed
``stop_decision`` port.

Mirrors the previous ``StandardStopExecutor`` non-failure branch:
falls back to ``StopDecision(should_stop=True, TASK_COMPLETED)`` when no
``stop_policy`` is wired.
"""

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
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    Reflection,
)
from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.runtime.runtime.runtime import StopPolicy
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class StopShouldCheckExecutor:
    """Primitive: invoke stop_policy, emit typed ``stop_decision`` port."""

    semantic_name: str = "phase.stop.should_check"
    region: str = "phase:stop"
    declared_inputs: tuple[PortName, ...] = ("decision", "observation", "reflection")
    declared_outputs: tuple[PortName, ...] = ("stop_decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        policy = runtime.get("stop_policy")
        if not isinstance(policy, StopPolicy):
            return NodeOutput(
                port_values={
                    "stop_decision": StopDecision(
                        should_stop=True,
                        reason=StopReason.TASK_COMPLETED,
                    )
                },
                next_hint=None,
            )
        decision = input.port_values.get("decision")
        observation = input.port_values.get("observation")
        reflection = input.port_values.get("reflection")
        stop = policy.decide(
            runtime.get("agent_state"),
            decision if isinstance(decision, Decision) else None,
            observation if isinstance(observation, Observation) else None,
            reflection if isinstance(reflection, Reflection) else None,
        )
        return NodeOutput(port_values={"stop_decision": stop}, next_hint=None)


@plugin(
    id="phase.stop.should_check",
    provides=("phase:stop::phase.stop.should_check",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_phase_subgraph_parity.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_stop_should_check.checked", "phase_stop_should_check.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    del config
    ctx.provide("phase:stop::phase.stop.should_check", StopShouldCheckExecutor())


__all__ = ["StopShouldCheckExecutor", "setup"]
