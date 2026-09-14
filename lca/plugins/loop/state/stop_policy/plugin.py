"""Default stop policy plugin for the State cluster.

The stop phase is fixed by the cognitive loop. The decision rule used inside
that phase is a replaceable policy, not a peer cognitive primitive or an
``AgentGraph`` dependency. This module owns the complete standard termination
decision behind the narrow ``StopPolicy.decide`` seam.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType, ReflectionVerdict
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Decision, Observation, Reflection
from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import ArtifactClosure, StopPolicy
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.session.context.turn_control_reader import control_turns

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

    def __init__(
        self,
        artifact_closure: ArtifactClosure,
        *,
        runtime: object | None = None,
    ) -> None:
        self._artifact_closure = artifact_closure
        from lca.cognition.convergence.runtime import ConvergenceRuntime

        self._runtime = (
            runtime if isinstance(runtime, ConvergenceRuntime) else ConvergenceRuntime.default()
        )

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
        delivery_stop = self._delivery_satisfied_stop(state, decision, observation, reflection)
        if delivery_stop is not None:
            return delivery_stop
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
            # Deterministic tool failure (PermissionError, FileNotFoundError,
            # TypeError, etc., tagged ``failure_kind = "execution"`` by the
            # Body executor) means the model cannot make progress on this
            # path.  Stop the loop instead of cycling through 8 retries.
            deterministic_failure_stop = self._deterministic_failure_stop(observation)
            if deterministic_failure_stop is not None:
                return deterministic_failure_stop
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

    @staticmethod
    def _deterministic_failure_stop(
        observation: Observation | None,
    ) -> StopDecision | None:
        """Stop the loop when the last tool call hit a non-recoverable error.

        Returns ``StopDecision(reason=ERROR, status=FAILED)`` when the
        observation carries any of these deterministic-failure signals:

        - ``failure_kind == "execution"`` — Body's classifier tag for
          non-retryable errors (permission denied, file not found, type
          errors). This is the primary signal.
        - ``failure_kind == "transient"`` — explicitly retries. Not a
          stop signal on its own.
        - ``success=False`` with a non-empty ``error`` and no tag — a
          legacy observation pre-dating the classifier; treat as
          non-retryable to avoid the run_0d71855ae274 8-step loop.
        - ``success=False`` with neither error nor tag — same logic;
          the model cannot make progress on this path.
        """
        from lca.contracts.atoms.semantic.keys import (
            FAILURE_KIND,
            FAILURE_KIND_EXECUTION,
            FAILURE_KIND_TRANSIENT,
        )

        if observation is None or observation.success:
            return None
        extra = observation.extra if isinstance(observation.extra, dict) else {}
        failure_kind = extra.get(FAILURE_KIND)
        if failure_kind == FAILURE_KIND_TRANSIENT:
            return None
        if failure_kind == FAILURE_KIND_EXECUTION or failure_kind is None:
            error_text = (observation.error or "").strip()
            return StopDecision(
                should_stop=True,
                reason=StopReason.ERROR,
                status=TaskStatus.FAILED,
                final_output=error_text or None,
            )
        return None

    def _budget_exhausted_decision(
        self,
        observation: Observation | None,
        state: AgentState,
    ) -> StopDecision:
        evidence, verdict = self._runtime.evaluate_budget_and_emit(state)

        last_ok = observation is not None and observation.success
        final_output = self._artifact_closure.synthesize()
        if (
            final_output is None
            and last_ok
            and observation is not None
            and isinstance(observation.payload, str)
        ):
            final_output = observation.payload
        if verdict.kind == "grace_respond" and not final_output:
            final_output = self._runtime.synthesize(state, evidence)
        completed = last_ok or final_output or verdict.kind == "grace_respond"
        status = TaskStatus.COMPLETED if completed else TaskStatus.FAILED
        return StopDecision(
            should_stop=True,
            reason=StopReason.BUDGET_EXCEEDED,
            final_output=final_output,
            status=status,
        )

    def _delivery_satisfied_stop(
        self,
        state: AgentState,
        decision: Decision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StopDecision | None:
        """Backup for DeliverySatisfiedGate: stop when evidence is ready but model keeps tooling.

        Two triggers unlock ``should_stop`` here, in priority order:

        1. ``evidence.satisfied`` — the durable fold has enough signal
           (artifact present, producer success, or user-visible text).
           Source of truth for replays.
        2. ``observation.success`` — the latest in-flight tool call
           succeeded. Falls back to this when the fold is empty (e.g.
           ``state.control_turns`` not yet projected in this iteration)
           so the loop converges instead of burning budget on a
           cache-hit repetition of the same tool call.
        """
        if decision is None or reflection is None:
            return None
        if decision.action_type == ActionType.RESPOND:
            return None
        if reflection.verdict == ReflectionVerdict.NEEDS_CORRECTION:
            return None
        evidence = self._runtime.evidence(state)
        live_tool_ok = observation is not None and observation.success
        if not evidence.satisfied and not live_tool_ok:
            return None
        final_output = self._runtime.synthesize(state, evidence).strip()
        if not final_output:
            final_output = (self._artifact_closure.synthesize() or "").strip()
        if not final_output:
            return None
        return StopDecision(
            should_stop=True,
            reason=StopReason.TASK_COMPLETED,
            final_output=final_output,
            status=TaskStatus.COMPLETED,
        )

    @staticmethod
    def _recent_tool_failures(state: AgentState) -> int:
        failures = 0
        for view in reversed(control_turns(state)):
            if view.action_type not in {ActionType.USE_TOOL.value, ActionType.USE_TOOL}:
                break
            if view.observation_success is False:
                failures += 1
        return failures


@plugin(
    id="state.stop-policy.default",
    provides=["stop_policy"],
    requires=["artifact_closure", "convergence_runtime"],
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
    runtime = ctx.require("convergence_runtime")
    ctx.provide("stop_policy", DefaultStopPolicy(artifact_closure, runtime=runtime))


__all__ = ["Config", "DefaultStopPolicy", "setup"]
