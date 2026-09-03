"""Act-constrain control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
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


class ActConstrainExecutor:
    """Execute act-constrain control policy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Evaluate act-constrain control."""
        decision = context.decision
        if decision is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="action constraint needs a decision",
                    plugin_id="control.executor.act-constrain",
                ),
            )
        call_ids = [call.call_id for call in decision.tool_calls]
        if any(not call_id.strip() for call_id in call_ids):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="tool call id is required",
                    plugin_id="control.executor.act-constrain",
                ),
            )
        if len(set(call_ids)) != len(call_ids):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="tool call ids must be unique",
                    plugin_id="control.executor.act-constrain",
                ),
            )
        if any(call.timeout_s is not None and call.timeout_s <= 0 for call in decision.tool_calls):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="tool timeout must be positive",
                    plugin_id="control.executor.act-constrain",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="action constraints are satisfied",
                plugin_id="control.executor.act-constrain",
            ),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.act.constrain",
    Config=Config,
    provides=["control.act.constrain"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.ACT,
            role=ContributionRole.GOVERN,
            executor="control.act.constrain",
            output="act.constrain",
            order=2,
            aggregation="deny-on-any-deny",
        )
    ],
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION, control_slots=(ControlSlot.ACT_CONSTRAIN,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("decision.read", "action.constrain")),
        observability=EvidenceContract(descriptors=("control.act.constrain.verified",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("control.act.constrain",),
        emits=("control.act.constrain.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.act.constrain", ActConstrainExecutor())


__all__ = ["ActConstrainExecutor", "Config", "setup"]
