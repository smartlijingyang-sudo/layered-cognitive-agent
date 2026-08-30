"""Observe-checkpoint control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

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


class ObserveCheckpointExecutor:
    """Execute observe-checkpoint control policy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Evaluate observe-checkpoint control."""
        if context.state.step < 0:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.DENY,
                    detail="checkpoint step cannot be negative",
                    plugin_id="control.executor.observe-checkpoint",
                ),
            )
        reason = (
            getattr(context.checkpoint_reason, "value", str(context.checkpoint_reason))
            if context.checkpoint_reason
            else "periodic"
        )
        return PhaseResult(
            result_kind="control",
            payload=ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail=f"checkpoint is valid: {reason}",
                plugin_id="control.executor.observe-checkpoint",
            ),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="control.observe.checkpoint",
    Config=Config,
    provides=["control.observe.checkpoint"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.STOP,
            role=ContributionRole.OBSERVE,
            executor="control.observe.checkpoint",
            output="observe.checkpoint",
            order=1,
        )
    ],
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.observe.checkpoint", ObserveCheckpointExecutor())


__all__ = ["Config", "ObserveCheckpointExecutor", "setup"]
