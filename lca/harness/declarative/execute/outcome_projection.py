"""Present declarative terminal data as stable interpreter results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.result import ApprovalPendingError
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols.act.command_envelope import RunFact
from lca.contracts.protocols.declarative.declarative_common import (
    DeclarativeValidationError,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_execution import (
    DeclarativeRunOutcome,
    JournalCommitter,
    PhaseResult,
    PhaseRunCursor,
)
from lca.harness.declarative.controls.approval import ApprovalStateMachine, ApprovalTransition
from lca.harness.declarative.graph.traversal import PhaseTraversal


@dataclass(frozen=True, slots=True)
class PhaseVisit:
    node_id: str
    semantic_phase: SemanticPhase
    result_kind: str
    selected_edge: str | None


@dataclass(frozen=True, slots=True)
class InterpretationResult:
    """The traversal-level result of a compiled declarative plan."""

    state: AgentState
    artifact: object
    visits: tuple[PhaseVisit, ...]
    facts: tuple[RunFact, ...]
    terminal_node: str
    cursor: PhaseRunCursor | None = None
    outcome: DeclarativeRunOutcome | None = None


class RunOutcomeProjector:
    """Project every kind of declarative terminal data into one ``InterpretationResult``.

    Approval pauses and validation / execution failures are inlined here rather
    than split across satellite projectors: every terminal path lands in this
    module, owns one Journal commit shape, and shares the same ``InterpretationResult``
    contract. There is no second consumer of the prior ``ApprovalPauseProjection``
    or ``FailureOutcomeProjector`` types.
    """

    def __init__(self, journal: JournalCommitter) -> None:
        self._journal = journal

    def governed(
        self,
        *,
        node_id: str,
        state: AgentState,
        outcome: DeclarativeRunOutcome,
        visits: list[PhaseVisit],
        facts: list[RunFact],
    ) -> InterpretationResult:
        return InterpretationResult(
            state=state,
            artifact=None,
            visits=tuple(visits),
            facts=tuple(facts),
            terminal_node=node_id,
            cursor=outcome.cursor,
            outcome=outcome,
        )

    def completed(
        self,
        *,
        node_id: str,
        state: AgentState,
        traversal: PhaseTraversal,
        result: PhaseResult,
        artifact: object | None,
        visits: list[PhaseVisit],
        facts: list[RunFact],
    ) -> InterpretationResult:
        cursor = traversal.checkpoint(
            node_id=node_id,
            causation_refs=result.evidence_refs,
            state_step=getattr(state, "step", 0),
        )
        return InterpretationResult(
            state=state,
            artifact=artifact,
            visits=tuple(visits),
            facts=tuple(facts),
            terminal_node=node_id,
            cursor=cursor,
            outcome=DeclarativeRunOutcome(
                kind="completed",
                cursor=cursor,
                stop=_terminal_stop_decision_from_result(result),
                error_fact=None,
            ),
        )

    def approval_pending(
        self,
        error: ApprovalPendingError,
        *,
        traversal: PhaseTraversal,
        state: AgentState,
        current_node_id: str,
        plan_ref: str,
        visits: list[PhaseVisit],
        facts: list[RunFact],
        approval_resume_node: str | None,
    ) -> InterpretationResult:
        """Materialise one paused or failed declarative outcome from an approval error.

        Graph traversal supplies the current node and the plan-declared Think node.
        This method owns all approval-specific work: validate the declaration,
        derive a stable request identifier, fold the approval state machine, commit
        its facts, and checkpoint the reusable cursor.
        """
        if approval_resume_node is None:
            return self._missing_approval_resume(
                traversal=traversal,
                state=state,
                plan_ref=plan_ref,
                visits=visits,
                facts=facts,
            )

        approval_request = _approval_request(error)
        approval_id = str(
            approval_request.get("approval_id")
            or f"{plan_ref}:{approval_resume_node}:{traversal.visit_counts.get(current_node_id, 1)}"
        )
        approval_request["approval_id"] = approval_id
        machine = ApprovalStateMachine()
        transitions = (
            machine.apply("approval.requested", approval_id, payload=approval_request),
            machine.apply(
                "approval.waiting_input",
                approval_id,
                payload={"from_node": current_node_id},
            ),
        )
        approval_facts = tuple(
            _approval_fact(
                transition,
                plan_ref=plan_ref,
                node_id=approval_resume_node,
            )
            for transition in transitions
        )
        for fact in approval_facts:
            self._journal.commit_fact(fact, plan_ref=plan_ref, node_ref=approval_resume_node)

        traversal.artifacts.pop(SemanticPhase.THINK.value, None)
        traversal.reset_visit(approval_resume_node)
        cursor = traversal.checkpoint(
            node_id=approval_resume_node,
            state_step=getattr(state, "step", 0),
        )
        paused_fact = RunFact(
            fact_id=f"{plan_ref}:{approval_resume_node}:approval_pending",
            plan_ref=plan_ref,
            kind="run.paused",
            payload={
                "reason": "approval_pending",
                "error": str(error),
                "from_node": current_node_id,
            },
        )
        self._journal.commit_fact(paused_fact, plan_ref=plan_ref, node_ref=approval_resume_node)
        return InterpretationResult(
            state=state,
            artifact=None,
            visits=tuple(visits),
            facts=(*facts, *approval_facts, paused_fact),
            terminal_node=traversal.current_node_id,
            cursor=cursor,
            outcome=DeclarativeRunOutcome(
                kind="paused",
                cursor=cursor,
                stop=_stop_decision(should_stop=False),
                error_fact=paused_fact,
                approval_request=approval_request,
            ),
        )

    def _missing_approval_resume(
        self,
        *,
        traversal: PhaseTraversal,
        state: AgentState,
        plan_ref: str,
        visits: list[PhaseVisit],
        facts: list[RunFact],
    ) -> InterpretationResult:
        error = DeclarativeValidationError(
            "PG-008",
            "approval pause requires a declared approval resume node",
        )
        node_id = traversal.current_node_id
        cursor = traversal.checkpoint(
            node_id=node_id,
            state_step=getattr(state, "step", 0),
        )
        error_fact = RunFact(
            fact_id=f"{plan_ref}:{node_id}:validation_error",
            plan_ref=plan_ref,
            kind="run.failed",
            payload={
                "reason": "validation_error",
                "error": str(error),
                "error_code": error.code,
            },
        )
        self._journal.commit_fact(error_fact, plan_ref=plan_ref, node_ref=node_id)
        return InterpretationResult(
            state=state,
            artifact=None,
            visits=tuple(visits),
            facts=(*facts, error_fact),
            terminal_node=node_id,
            cursor=cursor,
            outcome=DeclarativeRunOutcome(
                kind="failed",
                cursor=cursor,
                stop=_stop_decision(should_stop=True),
                error_fact=error_fact,
            ),
        )

    def failed(
        self,
        error: Exception,
        *,
        traversal: PhaseTraversal,
        state: AgentState,
        plan_ref: str,
        visits: list[PhaseVisit],
        facts: list[RunFact],
        reason: str,
        error_code: str | None = None,
    ) -> InterpretationResult:
        """Record exactly one durable failure outcome for a terminal error."""

        node_id = traversal.current_node_id
        cursor = traversal.checkpoint(
            node_id=node_id,
            state_step=getattr(state, "step", 0),
        )
        payload: dict[str, object] = {"reason": reason, "error": str(error)}
        if error_code is not None:
            payload["error_code"] = error_code
        error_fact = RunFact(
            fact_id=f"{plan_ref}:{node_id}:{reason}",
            plan_ref=plan_ref,
            kind="run.failed",
            payload=payload,
        )
        self._journal.commit_fact(error_fact, plan_ref=plan_ref, node_ref=node_id)
        return InterpretationResult(
            state=state,
            artifact=None,
            visits=tuple(visits),
            facts=(*facts, error_fact),
            terminal_node=node_id,
            cursor=cursor,
            outcome=DeclarativeRunOutcome(
                kind="failed",
                cursor=cursor,
                stop=StopDecision(
                    should_stop=True,
                    reason=StopReason.TASK_COMPLETED,
                    final_output=None,
                ),
                error_fact=error_fact,
            ),
        )


def terminal_result(result: PhaseResult) -> bool:
    return bool(_terminal_stop_decision_from_result(result).should_stop)


def _terminal_stop_decision_from_result(result: PhaseResult) -> StopDecision:
    """Require the terminal phase to provide the typed stop protocol."""

    if not isinstance(result.payload, StopDecision):
        raise DeclarativeValidationError(
            "RT-002", "terminal phase must return StopDecision as its payload"
        )
    return result.payload


def _approval_request(exc: ApprovalPendingError) -> dict[str, Any]:
    raw_request: object = getattr(exc, "approval_request", None)
    if not isinstance(raw_request, dict):
        return {"type": "approval_pending", "error": str(exc)}
    return {str(key): value for key, value in raw_request.items()}


def _approval_fact(
    transition: ApprovalTransition,
    *,
    plan_ref: str,
    node_id: str,
) -> RunFact:
    return RunFact(
        fact_id=f"{plan_ref}:{transition.approval_id}:{transition.event}",
        plan_ref=plan_ref,
        kind=transition.event,
        payload={
            "approval_id": transition.approval_id,
            "previous": transition.previous.value if transition.previous is not None else None,
            "current": transition.current.value,
            "sequence": transition.sequence,
            "payload": dict(transition.payload),
        },
    )


def _stop_decision(*, should_stop: bool) -> StopDecision:
    return StopDecision(
        should_stop=should_stop,
        reason=StopReason.TASK_COMPLETED if should_stop else StopReason.CONTINUE,
        final_output=None,
    )


__all__ = [
    "InterpretationResult",
    "PhaseVisit",
    "RunOutcomeProjector",
    "terminal_result",
]
