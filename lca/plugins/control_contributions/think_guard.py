"""Think-guard control executor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.state import AgentState
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

_GATE_CONTRIBUTIONS = {
    "gate.repeat-tool-call": "RepeatToolCallGate",
    "gate.tool-loop-breaker": "ToolLoopBreakerGate",
}


def _is_known_action(decision: Decision) -> bool:
    """Return whether a decision uses the closed ActionType vocabulary."""
    try:
        ActionType(decision.action_type)
        return True
    except (ValueError, AttributeError):
        return False


def _latest_gate_event(state: AgentState) -> GateDecided | None:
    """Return the latest typed gate event."""
    # This is a simplified version - in reality we'd need to check plugin_id
    events = PerceiveState.from_agent_state(state).gate_decided
    return events[-1] if events else None


def _gate_verdict_kind(event: GateDecided) -> ControlVerdictKind:
    """Translate the pre-existing GateDecided vocabulary into ControlVerdict."""
    if event.verdict == "rewrite" or event.is_rewritten:
        return ControlVerdictKind.REWRITE
    if event.verdict == "deny":
        return ControlVerdictKind.STOP
    return ControlVerdictKind.ALLOW


class ThinkGuardExecutor:
    """Execute think-guard control policy."""

    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult:
        """Evaluate think-guard control."""
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
        event = _latest_gate_event(context.state)
        if event is None:
            return PhaseResult(
                result_kind="control",
                payload=ControlVerdict(
                    kind=ControlVerdictKind.ALLOW,
                    detail="decision gate contribution accepted",
                    plugin_id="control.executor.think-guard",
                ),
            )
        kind = _gate_verdict_kind(event)
        detail = event.rationale or (
            event.policy_fact.message if event.policy_fact is not None else event.verdict
        )
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
    provides=["control.think.guard"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_control_contributions.py",
    contributes=[
        PhaseContribution(
            phase=SemanticPhase.THINK,
            role=ContributionRole.GOVERN,
            executor="control.think.guard",
            output="think.guard",
            order=0,
            aggregation="deny-on-any-deny",
        )
    ],
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide("control.think.guard", ThinkGuardExecutor())


__all__ = ["Config", "ThinkGuardExecutor", "setup"]
