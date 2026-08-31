"""Act-execute control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot.control_slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.functional_group.functional_group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
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
from lca.harness.plugin.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class ActExecuteExecutor:
    """Execute act-execute control policy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Evaluate act-execute control."""
        decision = context.decision
        if decision is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="execution requires a decision",
                    plugin_id="control.executor.act-execute",
                ),
            )
        if decision.action_type == ActionType.USE_TOOL and not decision.tool_calls:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="tool execution has no calls",
                    plugin_id="control.executor.act-execute",
                ),
            )
        if (
            decision.action_type in {ActionType.DELEGATE, ActionType.HANDOFF}
            and not decision.delegations
        ):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="delegation execution has no target",
                    plugin_id="control.executor.act-execute",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="execution payload is complete",
                plugin_id="control.executor.act-execute",
            ),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.act.execute",
    Config=Config,
    provides=["control.act.execute"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.ACT,
            role=ContributionRole.GOVERN,
            executor="control.act.execute",
            output="act.execute",
            order=3,
            aggregation="deny-on-any-deny",
        )
    ],
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.ACT_EXECUTE,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(
            grants=("decision.read", "action.execute.govern"),
        ),
        observability=EvidenceContract(
            descriptors=("control.act.execute.verified",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("control.act.execute",),
        emits=("control.act.execute.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.act.execute", ActExecuteExecutor())


__all__ = ["ActExecuteExecutor", "Config", "setup"]
