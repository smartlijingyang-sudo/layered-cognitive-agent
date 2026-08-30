"""Act-safe-boundary control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ContributionRole,
    PhaseContext,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class ActSafeBoundaryExecutor:
    """Execute act-safe-boundary control policy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Evaluate act-safe-boundary control."""
        if context.state.status != TaskStatus.WORKING:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="non-working run cannot cross body boundary",
                    plugin_id="control.executor.act-safe-boundary",
                ),
            )
        decision = context.decision
        if decision is not None and decision.action_type == ActionType.STOP:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="decision requested terminal stop",
                    plugin_id="control.executor.act-safe-boundary",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="body boundary is safe",
                plugin_id="control.executor.act-safe-boundary",
            ),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.act.safe-boundary",
    Config=Config,
    provides=["control.act.safe-boundary"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.ACT,
            role=ContributionRole.GOVERN,
            executor="control.act.safe-boundary",
            output="act.safe-boundary",
            order=4,
            aggregation="deny-on-any-deny",
        )
    ],
    functional_group=FunctionalGroup.G6_DECISION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G6_DECISION,
        control_slot=ControlSlot.ACT_SAFE_BOUNDARY,
        scope=Scope.TURN,
        authority=("run.status.read", "effect.boundary.govern"),
        evidence=("control.act.safe-boundary.verified",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.act.safe-boundary", ActSafeBoundaryExecutor())


__all__ = ["ActSafeBoundaryExecutor", "Config", "setup"]
