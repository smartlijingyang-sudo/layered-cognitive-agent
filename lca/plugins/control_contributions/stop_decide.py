"""Stop-decide control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.enums import ActionType
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ContributionRole,
    PhaseContext,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class StopDecideExecutor:
    """Execute stop-decide control policy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Evaluate stop-decide control."""
        if context.state.budget.exceeded():
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="run budget is exhausted",
                    plugin_id="control.executor.stop-decide",
                ),
            )
        if context.decision is not None and context.decision.action_type == ActionType.STOP:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="decision requested terminal stop",
                    plugin_id="control.executor.stop-decide",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="stop rule may continue",
                plugin_id="control.executor.stop-decide",
            ),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.stop.decide",
    Config=Config,
    provides=["control.stop.decide"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.STOP,
            role=ContributionRole.GOVERN,
            executor="control.stop.decide",
            output="stop.decide",
            order=0,
            aggregation="deny-on-any-deny",
        )
    ],
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.STOP_DECIDE,
        scope=Scope.TURN,
        authority=("action.type.read",),
        evidence=("control.stop.decide.checked",),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('control.stop.decide',),
        emits=('control.stop.decide.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.stop.decide", StopDecideExecutor())


__all__ = ["Config", "StopDecideExecutor", "setup"]
