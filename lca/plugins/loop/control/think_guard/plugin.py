"""control.think.guard — NodeExecutor control node for the think.guard slot.

Provides two nodes: ``control.think.guard.enforce`` (transform) and
``control.think.guard`` (govern / verdict emission). Each implements
``NodeExecutor`` directly — no PhaseContribution, no PhaseExecutor.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
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
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def _is_known_action(decision: Decision) -> bool:
    try:
        ActionType(decision.action_type)
        return True
    except (ValueError, AttributeError):
        return False


def _verdict_from_decision(decision: Decision) -> tuple[ControlVerdictKind, str]:
    gate_verdict = decision.extra.get("gate_verdict")
    if isinstance(gate_verdict, str) and gate_verdict == "deny":
        return ControlVerdictKind.STOP, decision.rationale or gate_verdict
    if decision.degraded_from is not None:
        return (
            ControlVerdictKind.REWRITE,
            decision.rationale or f"rewritten from {decision.degraded_from}",
        )
    if isinstance(gate_verdict, str) and gate_verdict == "rewrite":
        return ControlVerdictKind.REWRITE, decision.rationale or gate_verdict
    return ControlVerdictKind.ALLOW, "decision gate contribution accepted"


@dataclass(frozen=True, slots=True)
class ThinkGuardEnforceExecutor:
    """Transform node: run profile-selected decision gates."""

    semantic_name: str = "control.think.guard.enforce"
    region: str = "phase:think"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        decision = input.port_values.get("decision")
        if not isinstance(decision, Decision):
            return NodeOutput(port_values={"decision": None}, next_hint=None)
        gate_service = runtime.get("gates")
        if gate_service is None:
            return NodeOutput(port_values={"decision": decision}, next_hint=None)
        from lca.cognition.brain.gate.service import GateService

        if not isinstance(gate_service, GateService):
            raise TypeError(
                "phase capability 'gates' must be GateService, "
                f"got {type(gate_service).__name__}"
            )
        enforced = await gate_service.assemble().enforce(runtime.get("agent_state"), decision)
        return NodeOutput(port_values={"decision": enforced}, next_hint=None)


@dataclass(frozen=True, slots=True)
class ThinkGuardExecutor:
    """Govern node: enforce action-type + gate verdict; emit ``verdict``."""

    semantic_name: str = "control.think.guard"
    region: str = "phase:think"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("verdict",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context
        decision = input.port_values.get("decision")
        if not isinstance(decision, Decision):
            verdict = ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="candidate decision not materialized",
                plugin_id="control.executor.think-guard",
            )
            return NodeOutput(port_values={"verdict": verdict}, next_hint=None)
        if not _is_known_action(decision):
            verdict = ControlVerdict(
                kind=ControlVerdictKind.STOP,
                detail="candidate action type is unknown",
                plugin_id="control.executor.think-guard",
            )
            return NodeOutput(
                port_values={"verdict": verdict}, next_hint="stop"
            )
        kind, detail = _verdict_from_decision(decision)
        verdict = ControlVerdict(
            kind=kind,
            detail=detail,
            plugin_id="control.executor.think-guard",
        )
        hint = "stop" if kind == ControlVerdictKind.STOP else None
        return NodeOutput(port_values={"verdict": verdict}, next_hint=hint)


@plugin(
    id="control.think.guard",
    provides=(
        "phase:think::control.think.guard.enforce",
        "phase:think::control.think.guard",
    ),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.THINK_GUARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("decision.read", "gates.assemble")),
        observability=EvidenceContract(
            descriptors=("control_think_guard.checked", "control_think_guard.served")
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
    ctx.provide("phase:think::control.think.guard.enforce", ThinkGuardEnforceExecutor())
    ctx.provide("phase:think::control.think.guard", ThinkGuardExecutor())


__all__ = [
    "ThinkGuardEnforceExecutor",
    "ThinkGuardExecutor",
    "setup",
]
