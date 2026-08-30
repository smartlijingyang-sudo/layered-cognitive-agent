"""Perceive-context control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.models.core.lifecycle import TaskStatus
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


class PerceiveContextExecutor:
    """Execute perceive-context control policy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Evaluate perceive-context control."""
        state = context.state
        if state.status != TaskStatus.WORKING:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.STOP,
                    detail="run state is not working",
                    plugin_id="control.executor.perceive-context",
                ),
            )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="context assembly is permitted",
                plugin_id="control.executor.perceive-context",
            ),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.perceive.context",
    Config=Config,
    provides=["control.perceive.context"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.PERCEIVE,
            role=ContributionRole.GOVERN,
            executor="control.perceive.context",
            output="perceive.context",
            order=0,
            aggregation="deny-on-any-deny",
        )
    ],
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.perceive.context", PerceiveContextExecutor())


__all__ = ["Config", "PerceiveContextExecutor", "setup"]
