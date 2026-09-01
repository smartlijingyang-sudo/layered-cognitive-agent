"""Default stop policy plugin for the State cluster.

The stop phase is fixed by the cognitive loop. The decision rule used inside
that phase is a replaceable policy, not a peer cognitive primitive or an
``AgentGraph`` dependency. This module owns the complete standard termination
decision behind the narrow ``StopPolicy.decide`` seam.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import ActionType, ReflectionVerdict
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
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols import ArtifactClosure, StopPolicy
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_FALSE_COMPLETION_WINDOW = 3


class Config(BaseModel):
    """Default stop-policy configuration."""

    model_config = {"extra": "forbid"}


class DefaultStopPolicy(StopPolicy):
    """Standard pure termination policy for the fixed stop phase.

    The policy hides completion and budget-exhaustion rules behind one narrow
    interface. It returns an immutable ``StopDecision`` only; the reducer
    remains the sole writer of terminal state.
    """

    def __init__(self, artifact_closure: ArtifactClosure) -> None:
        self._artifact_closure = artifact_closure

    def decide(
        self,
        state: AgentState,
        decision: Decision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StopDecision:
        completed = self._completed_decision(state, decision, observation, reflection)
        if completed is not None:
            return completed
        if state.budget.exceeded():
            return self._budget_exhausted_decision(observation, state)
        return StopDecision()

    def _completed_decision(
        self,
        state: AgentState,
        decision: Decision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StopDecision | None:
        if decision is None or reflection is None:
            return None
        degraded_ok = bool(
            observation is not None and observation.success and observation.degraded_from
        )
        if decision.action_type == ActionType.HANDOFF:
            return StopDecision(
                should_stop=True,
                reason=StopReason.TASK_COMPLETED,
                status=TaskStatus.COMPLETED,
            )
        if decision.action_type != ActionType.RESPOND and not degraded_ok:
            return None
        final_output = decision.response_text or self._degraded_output(observation, degraded_ok)
        should_stop = reflection.verdict != ReflectionVerdict.NEEDS_CORRECTION
        if should_stop and self._recent_tool_failures(state) >= _FALSE_COMPLETION_WINDOW:
            should_stop = False
        if not should_stop:
            return None
        return StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output=final_output,
            status=TaskStatus.COMPLETED,
        )

    @staticmethod
    def _degraded_output(observation: Observation | None, degraded_ok: bool) -> str | None:
        if degraded_ok and observation is not None and isinstance(observation.payload, str):
            return observation.payload
        return None

    def _budget_exhausted_decision(
        self,
        observation: Observation | None,
        state: AgentState,
    ) -> StopDecision:
        last_ok = observation is not None and observation.success
        final_output = self._artifact_closure.synthesize()
        # ADR-0158 决策 四:AgentState.final_output 字段已删除;
        # fallback 链改为 Stop决策.last_output_ref(预留)或 observation.payload。
        if (
            final_output is None
            and last_ok
            and observation is not None
            and isinstance(observation.payload, str)
        ):
            final_output = observation.payload
        status = TaskStatus.COMPLETED if (last_ok or final_output) else TaskStatus.FAILED
        return StopDecision(
            should_stop=True,
            reason=StopReason.BUDGET_EXCEEDED,
            final_output=final_output,
            status=status,
        )

    @staticmethod
    def _recent_tool_failures(state: AgentState) -> int:
        failures = 0
        for turn in reversed(state.history):
            if turn.decision.action_type != ActionType.USE_TOOL:
                break
            if turn.observation is not None and not turn.observation.success:
                failures += 1
        return failures


@plugin(
    id="state.stop-policy.default",
    provides=["stop_policy"],
    requires=["artifact_closure"],
    implements=[StopPolicy],
    layer="L2",
    effects="none",
    description="Provide the standard State-cluster stop policy for the fixed stop phase.",
    test_suite="tests/plugins/state/test_stop_policy.py",
    kind=PluginKind.PROVIDER,
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v2"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G3_FACTS, control_slots=(ControlSlot.STOP_DECIDE,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("stop_policy.read",)),
        observability=EvidenceContract(descriptors=("policy.stop.default.stopped",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("stop_policy",),
        emits=("stop_policy.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the profile-selected standard termination policy."""

    del config
    artifact_closure: ArtifactClosure = ctx.require("artifact_closure")
    ctx.provide("stop_policy", DefaultStopPolicy(artifact_closure))


__all__ = ["Config", "DefaultStopPolicy", "setup"]
