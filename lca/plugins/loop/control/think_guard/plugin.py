"""Think-guard control executors — gate enforcement via declarative phase graph."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.cognition.gate_service import GateService
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import ActionType
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
from lca.contracts.models.core.decision import Decision
from lca.contracts.protocols.declarative.declarative_execution import StandardPhaseCapability
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ContributionRole,
    PhaseContext,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def _is_known_action(decision: Decision) -> bool:
    """Return whether a decision uses the closed ActionType vocabulary."""
    try:
        ActionType(decision.action_type)
        return True
    except (ValueError, AttributeError):
        return False


def _resolve_gate_service(context: PhaseContext) -> GateService | None:
    """Return the profile-selected gate registry when declared to the phase."""
    gates = context.capabilities.get(StandardPhaseCapability.GATES.value)
    if gates is None:
        return None
    if not isinstance(gates, GateService):
        raise TypeError(
            "phase capability 'gates' must be GateService, "
            f"got {type(gates).__name__}"
        )
    return gates


def _verdict_from_decision(decision: Decision) -> tuple[ControlVerdictKind, str]:
    """Derive control verdict from the enforced Decision artifact (ADR-0194 D3)."""
    gate_verdict = decision.extra.get("gate_verdict")
    if isinstance(gate_verdict, str) and gate_verdict == "deny":
        return ControlVerdictKind.STOP, decision.rationale or gate_verdict
    if decision.degraded_from is not None:
        return ControlVerdictKind.REWRITE, decision.rationale or f"rewritten from {decision.degraded_from}"
    if isinstance(gate_verdict, str) and gate_verdict == "rewrite":
        return ControlVerdictKind.REWRITE, decision.rationale or gate_verdict
    return ControlVerdictKind.ALLOW, "decision gate contribution accepted"


class ThinkGuardEnforceExecutor:
    """Run profile-selected decision gates and return the enforced Decision."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        decision = context.decision
        if decision is None:
            return PhaseResult(result_kind="decision", payload=None)
        gate_service = _resolve_gate_service(context)
        if gate_service is None:
            return PhaseResult(result_kind="decision", payload=decision)
        enforced = await gate_service.assemble().enforce(context.state, decision)
        return PhaseResult(result_kind="decision", payload=enforced)


class ThinkGuardExecutor:
    """Map enforced Decision artifacts to the closed ControlVerdict vocabulary."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        decision = context.decision
        if decision is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.ALLOW,
                    detail="candidate decision not materialized",
                    plugin_id="control.executor.think-guard",
                ),
            )
        if not _is_known_action(decision):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="candidate action type is unknown",
                    plugin_id="control.executor.think-guard",
                ),
            )
        kind, detail = _verdict_from_decision(decision)
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=kind,
                detail=detail,
                plugin_id="control.executor.think-guard",
            ),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.think.guard",
    Config=Config,
    provides=["control.think.guard", "control.think.guard.enforce"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.THINK,
            role=ContributionRole.TRANSFORM,
            executor="control.think.guard.enforce",
            output="think.guard.enforce",
            order=0,
        ),
        PhaseContribution(
            phase=SemanticPhase.THINK,
            role=ContributionRole.GOVERN,
            executor="control.think.guard",
            output="think.guard",
            order=1,
            aggregation="deny-on-any-deny",
        ),
    ],
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION, control_slots=(ControlSlot.THINK_GUARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("decision.read", "gates.assemble")),
        observability=EvidenceContract(descriptors=("control.think.guard.checked",)),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("control.think.guard", "gates"),
        emits=("control.think.guard.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.think.guard.enforce", ThinkGuardEnforceExecutor())
    ctx.provide("control.think.guard", ThinkGuardExecutor())


__all__ = [
    "Config",
    "ThinkGuardEnforceExecutor",
    "ThinkGuardExecutor",
    "setup",
]
