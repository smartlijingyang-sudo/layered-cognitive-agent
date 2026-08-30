"""Apply typed declarative phase contributions and governance outcomes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.command_envelope import RunFact
from lca.contracts.protocols.control_verdict import ControlVerdict, ControlVerdictKind
from lca.contracts.protocols.declarative_phase_graph import (
    ContributionRole,
    DeclarativeRunOutcome,
    DeclarativeValidationError,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.declarative.assembler import ExecutableNode
from lca.harness.declarative.phase_context import RestrictedPhaseContext
from lca.harness.declarative.traversal import PhaseTraversal


@dataclass(frozen=True, slots=True)
class GovernanceResult:
    """The combined phase result and any terminal decision from contributions."""

    result: PhaseResult
    outcome: DeclarativeRunOutcome | None = None
    facts: tuple[RunFact, ...] = ()


class PhaseGovernance:
    """Apply declared contributions while delegating verdict policy to one module."""

    async def apply(
        self,
        executable_node: ExecutableNode,
        context: RestrictedPhaseContext,
        result: PhaseResult,
        *,
        plan_ref: str,
        node_id: str,
        traversal: PhaseTraversal,
    ) -> GovernanceResult:
        """Run contributions after a phase without owning effect or reducer work."""
        combined = result
        for contribution in executable_node.contributions:
            role = contribution.declaration.role
            if role is ContributionRole.PREPARE:
                continue
            contribution_context = self._contribution_context(executable_node, context, combined)
            outcome = await contribution.executor.execute(
                contribution_context,
                PhaseInput(artifact=combined.payload, causation_refs=combined.evidence_refs),
            )
            self._require_phase_result(contribution.declaration.executor, outcome)
            if role is ContributionRole.GOVERN:
                interpretation = interpret_control_verdict(
                    payload=outcome.payload,
                    contribution=contribution.declaration.executor,
                    plan_ref=plan_ref,
                    node_id=node_id,
                    result=combined,
                    traversal=traversal,
                    state=context.state,
                )
                if interpretation.outcome is not None:
                    facts: tuple[RunFact, ...] = ()
                    if interpretation.fact is not None:
                        context.journal.commit_fact(
                            interpretation.fact,
                            plan_ref=plan_ref,
                            node_ref=node_id,
                        )
                        facts = (interpretation.fact,)
                    return GovernanceResult(
                        result=combined,
                        outcome=interpretation.outcome,
                        facts=facts,
                    )
                if interpretation.fact is not None:
                    combined = replace(combined, facts=(*combined.facts, interpretation.fact))
            if (
                role in {ContributionRole.TRANSFORM, ContributionRole.FINALIZE}
                and outcome.payload is not None
            ):
                combined = replace(
                    combined,
                    result_kind=outcome.result_kind,
                    payload=outcome.payload,
                    command_envelope=outcome.command_envelope or combined.command_envelope,
                )
            combined = replace(
                combined,
                facts=(*combined.facts, *outcome.facts),
                deltas=(*combined.deltas, *outcome.deltas),
                evidence_refs=(*combined.evidence_refs, *outcome.evidence_refs),
            )
        return GovernanceResult(result=combined)

    @staticmethod
    async def prepare_input(
        executable_node: ExecutableNode,
        context: RestrictedPhaseContext,
        phase_input: PhaseInput,
    ) -> PhaseInput:
        """Apply declared prepare contributions before the main phase executor."""
        prepared = phase_input
        for contribution in executable_node.contributions:
            if contribution.declaration.role is not ContributionRole.PREPARE:
                continue
            outcome = await contribution.executor.execute(context, prepared)
            PhaseGovernance._require_phase_result(contribution.declaration.executor, outcome)
            if outcome.command_envelope is not None:
                raise DeclarativeValidationError(
                    "PG-003", "prepare contribution may not execute an effect"
                )
            if outcome.payload is not None:
                prepared = PhaseInput(
                    artifact=outcome.payload,
                    causation_refs=outcome.evidence_refs,
                )
        return prepared

    @staticmethod
    def _contribution_context(
        executable_node: ExecutableNode,
        context: RestrictedPhaseContext,
        result: PhaseResult,
    ) -> RestrictedPhaseContext:
        decision = context.artifacts.get("think")
        observation = context.artifacts.get("act")
        reflection = context.artifacts.get("reflect")
        return replace(
            context,
            decision=(
                result.payload
                if executable_node.semantic_phase is SemanticPhase.THINK
                and isinstance(result.payload, Decision)
                else decision
                if isinstance(decision, Decision)
                else None
            ),
            observation=(
                result.payload
                if executable_node.semantic_phase is SemanticPhase.ACT
                and isinstance(result.payload, Observation)
                else observation
                if isinstance(observation, Observation)
                else None
            ),
            reflection=(
                result.payload
                if executable_node.semantic_phase is SemanticPhase.REFLECT
                and isinstance(result.payload, Reflection)
                else reflection
                if isinstance(reflection, Reflection)
                else None
            ),
            checkpoint_reason=f"phase:{executable_node.node_id}",
        )

    @staticmethod
    def _require_phase_result(capability: str, outcome: object) -> None:
        if not isinstance(outcome, PhaseResult):
            raise DeclarativeValidationError(
                "RT-002", f"contribution returned non-PhaseResult: {capability}"
            )


@dataclass(frozen=True, slots=True)
class ControlVerdictInterpretation:
    """One govern contribution interpreted without leaking policy to callers.

    ``fact`` is evidence for every non-allow control decision. ``outcome`` is
    present only when the verdict blocks graph traversal; a rewrite remains a
    non-blocking request until a declared transform contribution replaces the
    phase payload.
    """

    verdict: ControlVerdict
    fact: RunFact | None = None
    outcome: DeclarativeRunOutcome | None = None


def interpret_control_verdict(
    *,
    payload: object,
    contribution: str,
    plan_ref: str,
    node_id: str,
    result: PhaseResult,
    traversal: PhaseTraversal,
    state: AgentState,
) -> ControlVerdictInterpretation:
    """Turn one typed control verdict into evidence and, when needed, an outcome.

    This is the sole harness mapping from the closed verdict vocabulary to graph
    traversal. It records rewrite requests without pretending that a control
    verdict can rewrite data by itself; a declared transform contribution owns
    any replacement payload.
    """
    verdict = _require_control_verdict(payload)
    if verdict.kind is ControlVerdictKind.ALLOW:
        return ControlVerdictInterpretation(verdict=verdict)

    fact_kind, outcome_kind, stop, approval_request = _verdict_resolution(
        verdict,
        contribution,
        result=result,
    )
    fact = RunFact(
        fact_id=f"{plan_ref}:{node_id}:{fact_kind}",
        plan_ref=plan_ref,
        kind=fact_kind,
        payload={
            "contribution": contribution,
            "verdict": verdict.kind.value,
            "detail": verdict.detail,
        },
    )
    if outcome_kind is None:
        return ControlVerdictInterpretation(verdict=verdict, fact=fact)
    if stop is None:
        raise DeclarativeValidationError(
            "RT-004", "terminal control verdict must provide a StopDecision"
        )

    cursor = traversal.checkpoint(
        node_id=node_id,
        causation_refs=result.evidence_refs,
        state_step=getattr(state, "step", 0),
    )
    return ControlVerdictInterpretation(
        verdict=verdict,
        fact=fact,
        outcome=DeclarativeRunOutcome(
            kind=outcome_kind,
            cursor=cursor,
            stop=stop,
            error_fact=fact if outcome_kind == "failed" else None,
            approval_request=approval_request,
        ),
    )


def classify_control_verdict(
    payload: object,
) -> Literal["allow", "deny", "rewrite", "pause", "stop"]:
    """Map the closed control verdict vocabulary to its public category."""
    verdict = _require_control_verdict(payload)
    kind_map: dict[ControlVerdictKind, Literal["allow", "deny", "rewrite", "pause", "stop"]] = {
        ControlVerdictKind.ALLOW: "allow",
        ControlVerdictKind.DENY: "deny",
        ControlVerdictKind.EXHAUSTED: "stop",
        ControlVerdictKind.STOP: "stop",
        ControlVerdictKind.ASK_HUMAN: "pause",
        ControlVerdictKind.REWRITE: "rewrite",
    }
    return kind_map[verdict.kind]


def control_stop_decision(
    *,
    should_stop: bool,
    reason: StopReason | None = None,
    status: TaskStatus | None = None,
    final_output: str | None = None,
) -> StopDecision:
    """Create the terminal marker used for governance-originated outcomes."""
    return StopDecision(
        should_stop=should_stop,
        reason=reason or (StopReason.TASK_COMPLETED if should_stop else StopReason.CONTINUE),
        final_output=final_output,
        status=status,
    )


def _verdict_resolution(
    verdict: ControlVerdict,
    contribution: str,
    *,
    result: PhaseResult,
) -> tuple[
    str,
    Literal["completed", "paused", "failed"] | None,
    StopDecision | None,
    dict[str, object] | None,
]:
    """Return the explicit evidence and terminal semantics for one verdict."""
    if verdict.kind is ControlVerdictKind.DENY:
        return (
            "control.denied",
            "failed",
            control_stop_decision(
                should_stop=True,
                reason=StopReason.ERROR,
                status=TaskStatus.FAILED,
            ),
            None,
        )
    if verdict.kind is ControlVerdictKind.EXHAUSTED:
        return (
            "control.exhausted",
            "failed",
            control_stop_decision(
                should_stop=True,
                reason=StopReason.BUDGET_EXCEEDED,
                status=TaskStatus.FAILED,
            ),
            None,
        )
    if verdict.kind is ControlVerdictKind.STOP:
        return (
            "control.stopped",
            "completed",
            control_stop_decision(
                should_stop=True,
                reason=StopReason.TASK_COMPLETED,
                status=TaskStatus.COMPLETED,
                final_output=_existing_stop_output(result),
            ),
            None,
        )
    if verdict.kind is ControlVerdictKind.ASK_HUMAN:
        return (
            "control.paused",
            "paused",
            control_stop_decision(
                should_stop=False,
                reason=StopReason.CONTINUE,
                status=TaskStatus.INPUT_REQUIRED,
            ),
            {
                "type": "control_paused",
                "contribution": contribution,
                "verdict": verdict.kind.value,
                "detail": verdict.detail,
            },
        )
    if verdict.kind is ControlVerdictKind.REWRITE:
        return "control.rewrite_requested", None, None, None
    raise DeclarativeValidationError("RT-004", f"unsupported control verdict: {verdict.kind!r}")


def _existing_stop_output(result: PhaseResult) -> str | None:
    """Preserve a terminal phase's output when a later control policy closes it."""

    payload = result.payload
    return payload.final_output if isinstance(payload, StopDecision) else None


def _require_control_verdict(payload: object) -> ControlVerdict:
    if not isinstance(payload, ControlVerdict):
        raise DeclarativeValidationError(
            "RT-004",
            "govern contribution must return a ControlVerdict payload",
        )
    return payload


__all__ = [
    "ControlVerdictInterpretation",
    "GovernanceResult",
    "PhaseGovernance",
    "classify_control_verdict",
    "control_stop_decision",
    "interpret_control_verdict",
]
