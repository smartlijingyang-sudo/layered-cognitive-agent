"""phase.remember.write — primitive: mint memory envelope + dispatch via gateway.

ADR-0221: reads typed ``decision`` / ``observation`` / ``reflection``
ports from upstream phases and mints a typed ``CommandEnvelope`` to the
memory effect seam via the runtime-injected ``effect_gateway``.
Effect dispatch is the C10 single side-effect path — no in-host Journal
writes, no reducer calls.
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
from lca.contracts.protocols.act.command.envelope import CapabilityGrant, mint_envelope
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def _decision_id(decision: object) -> str:
    return getattr(decision, "decision_id", None) or "missing"


@dataclass(frozen=True, slots=True)
class RememberWriteExecutor:
    """Primitive: mint envelope + dispatch to ``effect_gateway``; emit envelope."""

    semantic_name: str = "phase.remember.write"
    region: str = "phase:remember"
    declared_inputs: tuple[PortName, ...] = ("decision", "observation", "reflection")
    declared_outputs: tuple[PortName, ...] = ("envelope",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        decision = input.port_values.get("decision")
        observation = input.port_values.get("observation")
        reflection = input.port_values.get("reflection")
        if decision is None or observation is None or reflection is None:
            return NodeOutput(port_values={"envelope": None}, next_hint=None)
        plan_ref = str(context.metadata.get("plan_ref", ""))
        node_id = str(context.metadata.get("node_id", "remember.write"))
        envelope = mint_envelope(
            plan_ref=plan_ref,
            scope_ref=node_id,
            decision=decision,
            provider="effect.memory",
            grant=CapabilityGrant(capability="memory.update", scope="run", effect_class="memory"),
            idempotency_key=f"{plan_ref}:{node_id}:{_decision_id(decision)}",
            metadata={
                "effect_class": "memory",
                "operation": "memory.update",
                "observation": observation,
                "reflection": reflection,
            },
        )
        gateway = runtime.get("effect_gateway")
        receipt: object | None = None
        if gateway is not None:
            receipt = await gateway.dispatch(envelope)
        # Forward both the envelope (typed side-effect wire) and the receipt
        # to the fold node so downstream can render a typed ``memory_receipt``.
        return NodeOutput(
            port_values={"envelope": envelope, "memory_receipt": receipt},
            next_hint=None,
        )


@plugin(
    id="phase.remember.write",
    provides=("phase:remember::phase.remember.write",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="memory",
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
            descriptors=("phase_remember_write.checked", "phase_remember_write.served")
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
    ctx.provide("phase:remember::phase.remember.write", RememberWriteExecutor())


__all__ = ["RememberWriteExecutor", "setup"]
