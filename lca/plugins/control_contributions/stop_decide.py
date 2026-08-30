"""Stop-decide control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.enums import ActionType
from lca.contracts.protocols.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative_phase_graph import (
    ContributionRole,
    PhaseContext,
    PhaseContribution,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


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
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.stop.decide", StopDecideExecutor())


__all__ = ["Config", "StopDecideExecutor", "setup"]
