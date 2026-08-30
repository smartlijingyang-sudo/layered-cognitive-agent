"""Interpret a compiled declarative phase graph.

The interpreter owns graph traversal, checkpoint/resume entry, and edge
selection. Each phase-node visit is delegated to ``PhaseExecutionTransaction``
and every terminal result is delegated to ``RunOutcomeProjector``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.act.command_envelope import RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeValidationError,
    DeltaReducer,
    EffectGateway,
    JournalCommitter,
    PhaseCapabilityReader,
    PhaseEdge,
    PhaseInput,
    PhaseResult,
    PhaseRunCursor,
)
from lca.contracts.protocols.gate.loop_guard import LoopGuardEvaluator
from lca.contracts.protocols.runtime.runtime_lifecycle import (
    RuntimeBudgetSnapshot,
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
    RuntimeLifecyclePublisher,
)
from lca.harness.declarative.assembler import ExecutablePlan
from lca.harness.declarative.loop_guard import DeclarativeLoopGuardEvaluator
from lca.harness.declarative.outcome_projection import (
    InterpretationResult,
    PhaseVisit,
    RunOutcomeProjector,
    terminal_result,
)
from lca.harness.declarative.phase_context import RestrictedPhaseContext
from lca.harness.declarative.phase_observation import NullPhaseObserver, PhaseObserver
from lca.harness.declarative.phase_transaction import PhaseExecutionTransaction
from lca.harness.declarative.predicate import evaluate_restricted_predicate
from lca.harness.declarative.traversal import PhaseTraversal
from lca.harness.declarative.validation import require_valid
from lca.harness.plan import compiled_run_plan_ref


@dataclass(slots=True)
class InMemoryJournalCommitter(JournalCommitter):
    """Deterministic committer for pure interpreter tests and local drivers."""

    facts: list[RunFact] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    observations: list[object] = field(default_factory=list)

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str:
        self.facts.append(fact)
        return fact.fact_id or f"{node_ref}:fact:{len(self.facts)}"

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        self.evidence.append(evidence_ref)
        return evidence_ref

    def commit_observation(self, observation: object, *, plan_ref: str, node_ref: str) -> str:
        self.observations.append(observation)
        return f"{node_ref}:observation:{len(self.observations)}"


class GenericPlanInterpreter:
    """Traverse an ``ExecutablePlan`` without reading executor internals.

    Graph concerns stay here: choose the next declared edge and maintain visit
    and edge budgets. Per-phase side effects remain in
    ``PhaseExecutionTransaction``; checkpointing and terminal protocol
    projection remain in ``RunOutcomeProjector``.
    """

    def __init__(
        self,
        *,
        journal: JournalCommitter | None = None,
        effect_gateway: EffectGateway | None = None,
        reducer: DeltaReducer | None = None,
        phase_observer: PhaseObserver | None = None,
        loop_guard_evaluator: LoopGuardEvaluator | None = None,
        lifecycle_publisher: RuntimeLifecyclePublisher | None = None,
    ) -> None:
        self._journal = journal or InMemoryJournalCommitter()
        self._transaction = PhaseExecutionTransaction(
            journal=self._journal,
            effect_gateway=effect_gateway,
            reducer=reducer,
            phase_observer=phase_observer or NullPhaseObserver(),
        )
        self._outcomes = RunOutcomeProjector(self._journal)
        self._loop_guard_evaluator = loop_guard_evaluator or DeclarativeLoopGuardEvaluator()
        self._lifecycle_publisher = lifecycle_publisher

    async def run(
        self,
        executable: ExecutablePlan,
        *,
        state: AgentState,
        input: PhaseInput | None = None,
        budget: Budget | None = None,
        capabilities: PhaseCapabilityReader | Mapping[str, object] | None = None,
        artifacts: Mapping[str, object] | None = None,
    ) -> InterpretationResult:
        """Execute a validated plan from its declared entry node."""

        return await self._drive(
            executable,
            state=state,
            input=input,
            budget=budget,
            capabilities=capabilities,
            artifacts=artifacts,
            resume_cursor=None,
        )

    async def resume(
        self,
        executable: ExecutablePlan,
        *,
        state: AgentState,
        cursor: PhaseRunCursor,
        input: PhaseInput | None = None,
        budget: Budget | None = None,
        capabilities: PhaseCapabilityReader | Mapping[str, object] | None = None,
    ) -> InterpretationResult:
        """Resume from a cursor after verifying that it belongs to this plan."""

        plan = executable.plan
        if not plan.phase_graph:
            raise DeclarativeValidationError("PG-001", "plan has no phase graph")
        require_valid(plan.validation_report)
        expected_plan_ref = compiled_run_plan_ref(plan)
        if getattr(cursor, "plan_ref", None) != expected_plan_ref:
            raise DeclarativeValidationError(
                "PG-008",
                "cursor plan_ref "
                f"{getattr(cursor, 'plan_ref', None)!r} does not match executable plan "
                f"{expected_plan_ref!r}",
            )
        return await self._drive(
            executable,
            state=state,
            input=input,
            budget=budget,
            capabilities=capabilities,
            artifacts=dict(cursor.artifacts),
            resume_cursor=cursor,
        )

    async def _drive(
        self,
        executable: ExecutablePlan,
        *,
        state: AgentState,
        input: PhaseInput | None,
        budget: Budget | None,
        capabilities: PhaseCapabilityReader | Mapping[str, object] | None,
        artifacts: Mapping[str, object] | None,
        resume_cursor: PhaseRunCursor | None,
    ) -> InterpretationResult:
        plan = executable.plan
        if not plan.phase_graph:
            raise DeclarativeValidationError("PG-001", "plan has no phase graph")
        require_valid(plan.validation_report)
        graph = plan.phase_graph
        node_by_id = {node.id: node for node in graph.nodes}
        traversal = (
            PhaseTraversal.resume(cursor=resume_cursor, input=input)
            if resume_cursor is not None
            else PhaseTraversal.start(
                plan_ref=compiled_run_plan_ref(plan),
                entry_node_id=graph.entry,
                artifacts=artifacts,
                input=input,
            )
        )
        current_state = state
        state_budget = getattr(current_state, "budget", None)
        runtime_budget = budget or (state_budget if isinstance(state_budget, Budget) else Budget())
        facts: list[RunFact] = []
        visits: list[PhaseVisit] = []
        plan_ref = compiled_run_plan_ref(plan)

        try:
            while True:
                current_id = traversal.current_node_id
                node = node_by_id.get(current_id)
                executable_node = executable.nodes.get(current_id)
                if node is None or executable_node is None:
                    raise DeclarativeValidationError(
                        "PG-001", f"unassembled phase node: {current_id}"
                    )
                visit_count = traversal.visit(node_id=node.id, max_visits=node.max_visits)
                await self._publish_phase_event(
                    RuntimeLifecycleEventType.PHASE_STARTED,
                    node_id=node.id,
                    semantic_phase=node.semantic_phase,
                    state=current_state,
                    budget=runtime_budget,
                    plan_ref=plan_ref,
                )
                try:
                    transaction = await self._transaction.run(
                        node_id=node.id,
                        semantic_phase=node.semantic_phase,
                        executable_node=executable_node,
                        state=current_state,
                        budget=runtime_budget,
                        plan_ref=plan_ref,
                        traversal=traversal,
                        visit_count=visit_count,
                        capabilities=capabilities,
                        effect_policy=plan.effect_policy,
                    )
                except Exception:
                    await self._publish_phase_event(
                        RuntimeLifecycleEventType.PHASE_FAILED,
                        node_id=node.id,
                        semantic_phase=node.semantic_phase,
                        state=current_state,
                        budget=runtime_budget,
                        plan_ref=plan_ref,
                    )
                    raise
                current_state = transaction.state
                facts.extend(transaction.facts)
                result = transaction.result
                await self._publish_phase_event(
                    RuntimeLifecycleEventType.PHASE_COMPLETED,
                    node_id=node.id,
                    semantic_phase=node.semantic_phase,
                    state=current_state,
                    budget=runtime_budget,
                    plan_ref=plan_ref,
                    result_kind=result.result_kind,
                )
                if transaction.govern_outcome is not None:
                    visits.append(
                        PhaseVisit(node.id, node.semantic_phase, result.result_kind, None)
                    )
                    return self._outcomes.governed(
                        node_id=node.id,
                        state=current_state,
                        outcome=transaction.govern_outcome,
                        visits=visits,
                        facts=facts,
                    )
                if node.terminal and terminal_result(result):
                    visits.append(
                        PhaseVisit(node.id, node.semantic_phase, result.result_kind, None)
                    )
                    return self._outcomes.completed(
                        node_id=node.id,
                        state=current_state,
                        traversal=traversal,
                        result=result,
                        artifact=transaction.effective_payload,
                        visits=visits,
                        facts=facts,
                    )
                edge = self._select_edge(
                    graph.edges,
                    node.id,
                    result,
                    traversal.artifacts,
                    current_state,
                )
                if edge is None:
                    raise DeclarativeValidationError(
                        "PG-006", f"no validated next edge from node: {node.id}"
                    )
                visits.append(
                    PhaseVisit(node.id, node.semantic_phase, result.result_kind, edge.target)
                )
                traversal.advance(
                    edge=edge,
                    payload=transaction.effective_payload,
                    causation_refs=result.evidence_refs,
                )
        except Exception as exc:
            from lca.contracts.models.core.result import ApprovalPendingError

            if isinstance(exc, ApprovalPendingError):
                return self._outcomes.approval_pending(
                    exc,
                    traversal=traversal,
                    state=current_state,
                    current_node_id=current_id,
                    plan_ref=plan_ref,
                    visits=visits,
                    facts=facts,
                    approval_resume_node=graph.approval_resume_node,
                )
            if isinstance(exc, DeclarativeValidationError):
                return self._outcomes.failed(
                    exc,
                    traversal=traversal,
                    state=current_state,
                    plan_ref=plan_ref,
                    visits=visits,
                    facts=facts,
                    reason="validation_error",
                    error_code=exc.code,
                )
            return self._outcomes.failed(
                exc,
                traversal=traversal,
                state=current_state,
                plan_ref=plan_ref,
                visits=visits,
                facts=facts,
                reason="execution_error",
            )

    async def _publish_phase_event(
        self,
        event_type: RuntimeLifecycleEventType,
        *,
        node_id: str,
        semantic_phase: object,
        state: AgentState,
        budget: Budget,
        plan_ref: str,
        result_kind: str | None = None,
    ) -> None:
        """Publish one carrier-safe phase projection through the frozen passive seam."""

        publisher = self._lifecycle_publisher
        if publisher is None:
            return
        status = getattr(state, "status", TaskStatus.WORKING)
        if not isinstance(status, TaskStatus):
            status = TaskStatus.WORKING
        trace_id = getattr(state, "trace_id", "")
        if not isinstance(trace_id, str):
            trace_id = ""
        journal_sequence = getattr(self._journal, "sequence", None)
        if not isinstance(journal_sequence, int) or isinstance(journal_sequence, bool):
            journal_sequence = None
        phase_value = getattr(semantic_phase, "value", semantic_phase)
        if not isinstance(phase_value, str):
            phase_value = None
        await publisher.publish(
            RuntimeLifecycleEvent(
                type=event_type,
                trace_id=trace_id,
                plan_ref=plan_ref,
                status=status,
                step=int(getattr(state, "step", 0)),
                budget=RuntimeBudgetSnapshot(
                    max_tokens=budget.max_tokens,
                    max_cost_usd=budget.max_cost_usd,
                    max_steps=budget.max_steps,
                    max_wall_clock_seconds=budget.max_wall_clock_seconds,
                    used_tokens=budget.used_tokens,
                    used_cost_usd=budget.used_cost_usd,
                    used_steps=budget.used_steps,
                ),
                phase_cursor=node_id,
                journal_sequence=journal_sequence,
                semantic_phase=phase_value,
                result_kind=result_kind,
            )
        )

    def _apply_delta(self, state: AgentState, delta: RunDelta) -> AgentState:
        """Compatibility seam for focused tests of the reducer contract."""

        return self._transaction.apply_delta(state, delta)

    def _select_edge(
        self,
        edges: tuple[PhaseEdge, ...],
        source: str,
        result: PhaseResult,
        artifacts: dict[str, object],
        state: AgentState,
    ) -> PhaseEdge | None:
        """Choose the first matching edge admitted by its optional loop guard.

        A denied guarded edge is skipped rather than treated as the selected
        transition.  A topology may therefore declare a normal completion or
        escalation edge after a guarded re-entry edge without the interpreter
        knowing any phase-specific policy.
        """
        for edge in (edge for edge in edges if edge.source == source):
            if not evaluate_restricted_predicate(edge.when, result=result, artifacts=artifacts):
                continue
            if edge.loop is not None:
                verdict = self._loop_guard_evaluator.evaluate(
                    guard=edge.loop,
                    edge=edge,
                    state=state,
                    result=result,
                    artifacts=artifacts,
                )
                if not verdict.allow:
                    continue
            return edge
        return None


__all__ = [
    "GenericPlanInterpreter",
    "InMemoryJournalCommitter",
    "InterpretationResult",
    "PhaseVisit",
    "RestrictedPhaseContext",
]
