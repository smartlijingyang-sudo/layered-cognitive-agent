"""Act-authorize control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

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
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


def _is_known_action(decision: Decision) -> bool:
    """Return whether a decision uses the closed ActionType vocabulary."""
    try:
        ActionType(decision.action_type)
        return True
    except (ValueError, AttributeError):
        return False


class ActAuthorizeExecutor:
    """Execute act-authorize control policy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Evaluate act-authorize control."""
        decision = context.decision
        if decision is None or not _is_known_action(decision):
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="action type is not authorized",
                    plugin_id="control.executor.act-authorize",
                ),
            )
        if decision.action_type == ActionType.USE_TOOL:
            if not decision.tool_calls:
                return PhaseResult(
                    result_kind="control",
                    payload=ControlVerdict(
                        kind=ControlVerdictKind.DENY,
                        detail="tool action has no tool call",
                        plugin_id="control.executor.act-authorize",
                    ),
                )
            if any(not call.tool_name.strip() for call in decision.tool_calls):
                return PhaseResult(
                    result_kind="control",
                    payload=ControlVerdict(
                        kind=ControlVerdictKind.DENY,
                        detail="tool action has an unnamed tool",
                        plugin_id="control.executor.act-authorize",
                    ),
                )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="action shape is authorized",
                plugin_id="control.executor.act-authorize",
            ),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.act.authorize",
    Config=Config,
    provides=["control.act.authorize"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.ACT,
            role=ContributionRole.GOVERN,
            executor="control.act.authorize",
            output="act.authorize",
            order=0,
            aggregation="deny-on-any-deny",
        )
    ],
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION, control_slots=(ControlSlot.ACT_AUTHORIZE,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("decision.read", "action.authorize")),
        observability=EvidenceContract(descriptors=("control.act.authorize.verified",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("control.act.authorize",),
        emits=("control.act.authorize.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.act.authorize", ActAuthorizeExecutor())


__all__ = ["ActAuthorizeExecutor", "Config", "setup"]
