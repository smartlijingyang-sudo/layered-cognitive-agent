"""Commit the auditable work performed during one declarative phase visit."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.act.command_envelope import RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_execution import (
    PhaseAttemptFailure,
    PhaseExecutionFailure,
)
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeRunOutcome,
    DeclarativeValidationError,
    DeltaReducer,
    EffectDispatcher,
    EffectPolicyPlan,
    JournalCommitter,
    PhaseCapabilityReader,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.harness.declarative.compile.assembler import ExecutableNode
from lca.harness.declarative.compile.phase_capabilities import normalize_phase_capabilities
from lca.harness.declarative.compile.phase_execution_policy import execute_with_policy
from lca.harness.declarative.compile.phase_governance import GovernanceResult, PhaseGovernance
from lca.harness.declarative.controls.effect_receipt import adapt_effect_receipt
from lca.harness.declarative.graph.traversal import PhaseTraversal
from lca.harness.declarative.lifecycle.phase_context import RestrictedPhaseContext
from lca.harness.declarative.lifecycle.phase_observation import PhaseObserver, phase_state_snapshot


@dataclass(frozen=True, slots=True)
class PhaseTransactionResult:
    """The committed state, result, facts, and next artifact for one node visit."""

    state: AgentState
    result: PhaseResult
    effective_payload: object | None
    facts: tuple[RunFact, ...]
    govern_outcome: DeclarativeRunOutcome | None = None


def _failure_to_dict(failure: object) -> object:
    """Best-effort journal payload for :class:`PhaseExecutionFailure`.

    The RunFact payload field is a typed ``Mapping``; :class:`PhaseExecutionFailure`
    is a frozen dataclass that may not serialize cleanly under the journal's
    JSON contract. Serializing via ``dataclasses.asdict`` keeps the shape
    stable while every consumer (RuntimeObserved, reducer fallback, RunFact
    consumer) sees a regular mapping.
    """
    import dataclasses

    if isinstance(failure, PhaseExecutionFailure):
        return {
            "node_id": failure.node_id,
            "attempts": tuple(
                dataclasses.asdict(attempt)
                if isinstance(attempt, PhaseAttemptFailure)
                else {"attempt": getattr(attempt, "attempt", None)}
                for attempt in failure.attempts
            ),
            "attempt_count": len(failure.attempts),
        }
    if dataclasses.is_dataclass(failure):
        return dataclasses.asdict(failure)
    if isinstance(failure, Mapping):
        return dict(failure)
    # Strings and other scalars serialize to a single ``message`` field
    # so the journal never crashes on ``dict(string)``.
    return {"message": str(failure)}


class PhaseExecutionTransaction:
    """Run one node through explicit Journal, effect, and reducer seams.

    This type intentionally exposes ``run`` rather than ``execute``: it is a
    harness transaction, not a Layer-1 Action handler.
    """

    def __init__(
        self,
        *,
        journal: JournalCommitter,
        effect_gateway: EffectDispatcher | None,
        reducer: DeltaReducer | None,
        phase_observer: PhaseObserver,
    ) -> None:
        self._journal = journal
        self._effect_gateway = effect_gateway
        self._reducer = reducer
        self._phase_observer = phase_observer
        self._governance = PhaseGovernance()

    async def run(
        self,
        *,
        node_id: str,
        semantic_phase: SemanticPhase,
        executable_node: ExecutableNode,
        state: AgentState,
        budget: Budget,
        plan_ref: str,
        traversal: PhaseTraversal,
        visit_count: int,
        capabilities: PhaseCapabilityReader | Mapping[str, object] | None,
        effect_policy: EffectPolicyPlan | None,
    ) -> PhaseTransactionResult:
        """Prepare, run, govern, record, effect, and reduce one phase visit."""
        context = RestrictedPhaseContext(
            plan_ref=plan_ref,
            node_ref=node_id,
            state=state,
            journal=self._journal,
            budget=budget,
            artifacts=traversal.artifacts,
            capabilities=normalize_phase_capabilities(capabilities),
        )
        prepared = await self._governance.prepare_input(
            executable_node,
            context,
            traversal.next_input,
        )
        result = await execute_with_policy(
            node_id=executable_node.node_id,
            policy=executable_node.execution_policy,
            plan_ref=plan_ref,
            execute_attempt=lambda: self._run_executor(
                executable_node,
                context,
                prepared,
                semantic_phase=semantic_phase,
            ),
            budget=budget,
        )
        self._validate_result(semantic_phase, result)
        governance = (
            GovernanceResult(result=result)
            if result.result_kind == "phase_error"
            else await self._governance.apply(
                executable_node,
                context,
                result,
                plan_ref=plan_ref,
                node_id=node_id,
                traversal=traversal,
            )
        )
        if governance.outcome is not None:
            return PhaseTransactionResult(
                state=state,
                result=governance.result,
                effective_payload=None,
                facts=governance.facts,
                govern_outcome=governance.outcome,
            )

        result = governance.result
        self._validate_result(semantic_phase, result)
        # ``result.payload`` carries the typed failure detail
        # (e.g. :class:`PhaseExecutionFailure` with attempt history) for
        # ``result_kind == "phase_error"``. Surfacing it on the phase.result
        # fact keeps RuntimeObserved consumers and reducer fallbacks
        # informed without requiring a separate journal lookup.
        phase_payload: dict[str, object] = {
            "node": node_id,
            "semantic_phase": semantic_phase.value,
            "result_kind": result.result_kind,
        }
        if result.payload is not None:
            phase_payload["failure"] = _failure_to_dict(result.payload)
        phase_fact = RunFact(
            fact_id=f"{plan_ref}:{node_id}:{visit_count}",
            plan_ref=plan_ref,
            kind="phase.result",
            payload=phase_payload,
        )
        self._journal.commit_fact(phase_fact, plan_ref=plan_ref, node_ref=node_id)
        facts = [phase_fact]
        for fact in result.facts:
            self._journal.commit_fact(fact, plan_ref=plan_ref, node_ref=node_id)
            facts.append(fact)
        for evidence_ref in result.evidence_refs:
            self._journal.commit_evidence(evidence_ref, plan_ref=plan_ref, node_ref=node_id)
        effect_output = await self._run_effect(
            result,
            plan_ref=plan_ref,
            node_id=node_id,
            effect_policy=effect_policy,
        )
        for delta in (*result.deltas, *context.proposed_deltas):
            state = self.apply_delta(state, delta)
        return PhaseTransactionResult(
            state=state,
            result=result,
            effective_payload=traversal.record_result(
                semantic_phase=semantic_phase,
                result=result,
                effect_output=effect_output,
            ),
            facts=tuple(facts),
        )

    async def _run_executor(
        self,
        executable_node: ExecutableNode,
        context: RestrictedPhaseContext,
        prepared_input: PhaseInput,
        *,
        semantic_phase: SemanticPhase,
    ) -> PhaseResult:
        observation_state = phase_state_snapshot(context.state)
        with self._phase_observer.observe(
            semantic_phase=semantic_phase,
            state=observation_state,
        ):
            result = await executable_node.executor.execute(context, prepared_input)
        if not isinstance(result, PhaseResult):
            raise DeclarativeValidationError(
                "RT-002",
                f"executor returned non-PhaseResult: {executable_node.node_id}",
            )
        return result

    async def _run_effect(
        self,
        result: PhaseResult,
        *,
        plan_ref: str,
        node_id: str,
        effect_policy: EffectPolicyPlan | None,
    ) -> object | None:
        if result.command_envelope is None:
            return None
        if self._effect_gateway is None:
            raise DeclarativeValidationError("PG-003", "effectful result has no EffectDispatcher")
        if effect_policy is None:
            raise DeclarativeValidationError("PS-006", "effectful result has no EffectPolicy")
        if result.command_envelope.plan_ref != plan_ref:
            raise DeclarativeValidationError(
                "RT-003", "CommandEnvelope plan_ref does not match run plan"
            )
        receipt = adapt_effect_receipt(
            await self._effect_gateway.execute(result.command_envelope, effect_policy)
        )
        self._journal.commit_observation(receipt.audit_record, plan_ref=plan_ref, node_ref=node_id)
        return receipt.output

    def apply_delta(self, state: AgentState, delta: RunDelta) -> AgentState:
        """Apply a declared state change through the only permitted writer."""
        if self._reducer is None:
            raise DeclarativeValidationError(
                "RT-001",
                "phase produced a state delta but no DeltaReducer is configured",
            )
        if not isinstance(self._reducer, DeltaReducer):
            raise DeclarativeValidationError(
                "RT-001",
                "configured reducer must implement DeltaReducer.apply_delta",
            )
        return self._reducer.apply_delta(state, delta)

    @staticmethod
    def _validate_result(phase: SemanticPhase, result: PhaseResult) -> None:
        prohibited: dict[SemanticPhase, set[str]] = {
            SemanticPhase.PERCEIVE: {"decision", "command"},
            SemanticPhase.THINK: {"command"},
            SemanticPhase.ACT: {"state_mutation"},
            SemanticPhase.REFLECT: {"world_read"},
            SemanticPhase.REMEMBER: {"direct_memory_write"},
            SemanticPhase.STOP: {"process_exit"},
        }
        if result.result_kind in prohibited.get(phase, set()):
            raise DeclarativeValidationError(
                "RT-002",
                f"result kind {result.result_kind!r} violates {phase.value} contract",
            )
        if (
            phase is SemanticPhase.ACT
            and result.command_envelope is not None
            and not result.command_envelope.decision_ref
        ):
            raise DeclarativeValidationError(
                "PG-002", "act CommandEnvelope has no Decision reference"
            )


__all__ = ["PhaseExecutionTransaction", "PhaseTransactionResult"]
