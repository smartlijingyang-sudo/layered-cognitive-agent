"""ADR-0075 的通用声明式计划解释器。"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from lca.contracts.protocols.command_envelope import RunDelta, RunFact
from lca.contracts.protocols.declarative_phase_graph import (
    ContributionRole,
    DeclarativeRunOutcome,
    DeclarativeValidationError,
    EffectGateway,
    JournalCommitter,
    PhaseContext,
    PhaseInput,
    PhaseResult,
    PhaseRunCursor,
    SemanticPhase,
)
from lca.contracts.protocols.plan import compiled_run_plan_ref
from lca.contracts.models.core.result import ApprovalPendingError
from lca.harness.declarative.assembler import ExecutablePlan


@dataclass(slots=True)
class InMemoryJournalCommitter(JournalCommitter):
    """无外部 Journal 时可用的确定性 committer，主要供测试和纯驱动使用。"""

    facts: list[RunFact] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    observations: list[Any] = field(default_factory=list)

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str:
        self.facts.append(fact)
        return fact.fact_id or f"{node_ref}:fact:{len(self.facts)}"

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        self.evidence.append(evidence_ref)
        return evidence_ref

    def commit_observation(self, observation: Any, *, plan_ref: str, node_ref: str) -> str:
        self.observations.append(observation)
        return f"{node_ref}:observation:{len(self.observations)}"


@dataclass(slots=True)
class RestrictedPhaseContext(PhaseContext):
    """MTK 创建的最小阶段上下文；不持有可透传的 live scope。"""

    plan_ref: str
    node_ref: str
    state: Any
    journal: JournalCommitter
    budget: Any
    artifacts: Mapping[str, Any]
    capabilities: Any
    tracing: Any = None
    _proposed_deltas: list[RunDelta] = field(default_factory=list)

    def emit_fact(self, fact: RunFact) -> str:
        return str(self.journal.commit_fact(fact, plan_ref=self.plan_ref, node_ref=self.node_ref))

    def propose_delta(self, delta: RunDelta) -> None:
        self._proposed_deltas.append(delta)

    @property
    def proposed_deltas(self) -> tuple[RunDelta, ...]:
        return tuple(self._proposed_deltas)


@dataclass(frozen=True, slots=True)
class PhaseVisit:
    node_id: str
    semantic_phase: SemanticPhase
    result_kind: str
    selected_edge: str | None


@dataclass(frozen=True, slots=True)
class InterpretationResult:
    state: Any
    artifact: Any
    visits: tuple[PhaseVisit, ...]
    facts: tuple[RunFact, ...]
    terminal_node: str
    cursor: PhaseRunCursor | None = None
    outcome: DeclarativeRunOutcome | None = None


class GenericPlanInterpreter:
    """解释 ``ExecutablePlan``，不读取 executor 的私有属性或身份。"""

    def __init__(
        self,
        *,
        journal: JournalCommitter | None = None,
        effect_gateway: EffectGateway | None = None,
        reducer: Any | None = None,
    ) -> None:
        self._journal = journal or InMemoryJournalCommitter()
        self._effect_gateway = effect_gateway
        self._reducer = reducer

    async def run(
        self,
        executable: ExecutablePlan,
        *,
        state: Any,
        input: PhaseInput | None = None,
        budget: Any = None,
        capabilities: Any = None,
        artifacts: Mapping[str, Any] | None = None,
        tracing: Any = None,
    ) -> InterpretationResult:
        """Execute the plan from the beginning."""
        return await self._drive(
            executable,
            state=state,
            input=input,
            budget=budget,
            capabilities=capabilities,
            artifacts=artifacts,
            tracing=tracing,
            resume_cursor=None,
        )

    async def resume(
        self,
        executable: ExecutablePlan,
        *,
        state: Any,
        cursor: PhaseRunCursor,
        input: PhaseInput | None = None,
        budget: Any = None,
        capabilities: Any = None,
        tracing: Any = None,
    ) -> InterpretationResult:
        """Resume execution from a saved cursor position."""
        plan = executable.plan
        if not plan.phase_graph:
            raise DeclarativeValidationError("PG-001", "plan has no phase graph")
        plan.validation_report.require_valid()
        
        # Validate cursor belongs to this plan
        expected_plan_ref = compiled_run_plan_ref(plan)
        if cursor.plan_ref != expected_plan_ref:
            raise DeclarativeValidationError(
                "PG-008",
                f"cursor plan_ref {cursor.plan_ref!r} does not match executable plan {expected_plan_ref!r}",
            )
        
        return await self._drive(
            executable,
            state=state,
            input=input,
            budget=budget,
            capabilities=capabilities,
            artifacts=dict(cursor.artifacts),
            tracing=tracing,
            resume_cursor=cursor,
        )

    async def _drive(
        self,
        executable: ExecutablePlan,
        *,
        state: Any,
        input: PhaseInput | None,
        budget: Any,
        capabilities: Any,
        artifacts: Mapping[str, Any] | None,
        tracing: Any,
        resume_cursor: PhaseRunCursor | None,
    ) -> InterpretationResult:
        plan = executable.plan
        if not plan.phase_graph:
            raise DeclarativeValidationError("PG-001", "plan has no phase graph")
        plan.validation_report.require_valid()
        graph = plan.phase_graph
        node_by_id = {node.id: node for node in graph.nodes}
        
        # Resume from cursor or start from entry
        if resume_cursor is not None:
            current_id = resume_cursor.node_id
            visit_counts: dict[str, int] = dict(resume_cursor.visit_counts)
            edge_counts: dict[tuple[str, str], int] = dict(
                (k, v) for k, v in resume_cursor.edge_counts
            )
            artifact_map = dict(resume_cursor.artifacts)
            current_input = input or PhaseInput(
                artifact=artifact_map.get("payload"),
                causation_refs=resume_cursor.causation_refs,
            )
        else:
            current_id = graph.entry
            visit_counts = {}
            edge_counts = {}
            artifact_map = dict(artifacts or {})
            current_input = input or PhaseInput()
        
        current_state = state
        facts: list[RunFact] = []
        visits: list[PhaseVisit] = []
        plan_ref = compiled_run_plan_ref(plan)

        def _build_cursor(node_id: str, evidence_refs: tuple[str, ...] = ()) -> PhaseRunCursor:
            """Helper to build cursor at current execution point."""
            return PhaseRunCursor(
                plan_ref=plan_ref,
                node_id=node_id,
                visit_counts=tuple(sorted(visit_counts.items())),
                edge_counts=tuple(((k[0], k[1]), v) for k, v in edge_counts.items()),
                artifacts=dict(artifact_map),
                causation_refs=evidence_refs,
                budget_snapshot={"step": 0},
            )

        def _build_stop_decision(should_stop: bool = True) -> Any:
            """Build minimal stop decision for outcome."""
            from lca.contracts.models.core.stop import StopDecision, StopReason
            return StopDecision(
                should_stop=should_stop,
                reason=StopReason.TASK_COMPLETED if should_stop else StopReason.CONTINUE,
                final_output=None,
            )

        try:
            while True:
                node = node_by_id.get(current_id)
                executable_node = executable.nodes.get(current_id)
                if node is None or executable_node is None:
                    raise DeclarativeValidationError("PG-001", f"unassembled phase node: {current_id}")
                visit_counts[current_id] = visit_counts.get(current_id, 0) + 1
                if visit_counts[current_id] > node.max_visits:
                    raise DeclarativeValidationError("PG-007", f"node visit budget exhausted: {current_id}")
                context = RestrictedPhaseContext(
                    plan_ref=plan_ref,
                    node_ref=node.id,
                    state=current_state,
                    journal=self._journal,
                    budget=budget,
                    artifacts=artifact_map,
                    capabilities=capabilities,
                    tracing=tracing,
                )
                prepared_input = await self._prepare_input(executable_node, context, current_input)
                result = await executable_node.executor.execute(context, prepared_input)
                if not isinstance(result, PhaseResult):
                    raise DeclarativeValidationError("RT-002", f"executor returned non-PhaseResult: {node.id}")
                self._validate_result(node.semantic_phase, result)
                result, govern_outcome = await self._apply_post_contributions(
                    executable_node,
                    context,
                    result,
                    plan_ref=plan_ref,
                    node_id=node.id,
                )
                if govern_outcome is not None:
                    # Govern verdict caused early termination
                    visits.append(PhaseVisit(node.id, node.semantic_phase, result.result_kind, None))
                    return InterpretationResult(
                        state=current_state,
                        artifact=None,
                        visits=tuple(visits),
                        facts=tuple(facts),
                        terminal_node=node.id,
                        cursor=govern_outcome.cursor,
                        outcome=govern_outcome,
                    )
                self._validate_result(node.semantic_phase, result)
                phase_fact = RunFact(
                    fact_id=f"{plan_ref}:{node.id}:{visit_counts[node.id]}",
                    plan_ref=plan_ref,
                    kind="phase.result",
                    payload={
                        "node": node.id,
                        "semantic_phase": node.semantic_phase.value,
                        "result_kind": result.result_kind,
                    },
                )
                self._journal.commit_fact(phase_fact, plan_ref=plan_ref, node_ref=node.id)
                facts.append(phase_fact)
                for fact in result.facts:
                    self._journal.commit_fact(fact, plan_ref=plan_ref, node_ref=node.id)
                    facts.append(fact)
                for evidence_ref in result.evidence_refs:
                    self._journal.commit_evidence(evidence_ref, plan_ref=plan_ref, node_ref=node.id)
                effect_receipt = None
                if result.command_envelope is not None:
                    if self._effect_gateway is None:
                        raise DeclarativeValidationError("PG-003", "effectful result has no EffectGateway")
                    if plan.effect_policy is None:
                        raise DeclarativeValidationError("PS-006", "effectful result has no EffectPolicy")
                    if result.command_envelope.plan_ref != plan_ref:
                        raise DeclarativeValidationError("RT-003", "CommandEnvelope plan_ref does not match run plan")
                    effect_receipt = await self._effect_gateway.execute(result.command_envelope, plan.effect_policy)
                    self._journal.commit_observation(effect_receipt, plan_ref=plan_ref, node_ref=node.id)
                    artifact_map["observation"] = effect_receipt
                deltas = (*result.deltas, *context.proposed_deltas)
                for delta in deltas:
                    current_state = self._apply_delta(current_state, delta)
                effective_payload = result.payload if result.payload is not None else effect_receipt
                artifact_map["result"] = result
                artifact_map["payload"] = effective_payload
                artifact_map[node.semantic_phase.value] = effective_payload
                if node.terminal and _terminal_result(result):
                    visits.append(PhaseVisit(node.id, node.semantic_phase, result.result_kind, None))
                    cursor = _build_cursor(node.id, result.evidence_refs)
                    outcome = DeclarativeRunOutcome(
                        kind="completed",
                        cursor=cursor,
                        stop=_build_stop_decision(should_stop=True),
                        error_fact=None,
                    )
                    return InterpretationResult(
                        state=current_state,
                        artifact=effective_payload,
                        visits=tuple(visits),
                        facts=tuple(facts),
                        terminal_node=node.id,
                        cursor=cursor,
                        outcome=outcome,
                    )
                edge = self._select_edge(graph.edges, node.id, result, artifact_map)
                if edge is None:
                    raise DeclarativeValidationError("PG-006", f"no validated next edge from node: {node.id}")
                key = (edge.source, edge.target)
                edge_counts[key] = edge_counts.get(key, 0) + 1
                if edge.loop and edge_counts[key] > edge.loop.max_iterations:
                    raise DeclarativeValidationError("PG-007", f"loop edge budget exhausted: {edge.source}->{edge.target}")
                visits.append(PhaseVisit(node.id, node.semantic_phase, result.result_kind, edge.target))
                current_id = edge.target
                current_input = PhaseInput(artifact=effective_payload, causation_refs=result.evidence_refs)
        except ApprovalPendingError as exc:
            # Capture cursor at failure point and return paused outcome
            cursor = _build_cursor(current_id)
            error_fact = RunFact(
                fact_id=f"{plan_ref}:{current_id}:approval_pending",
                plan_ref=plan_ref,
                kind="run.paused",
                payload={"reason": "approval_pending", "error": str(exc)},
            )
            self._journal.commit_fact(error_fact, plan_ref=plan_ref, node_ref=current_id)
            facts.append(error_fact)
            outcome = DeclarativeRunOutcome(
                kind="paused",
                cursor=cursor,
                stop=_build_stop_decision(should_stop=False),
                error_fact=error_fact,
            )
            return InterpretationResult(
                state=current_state,
                artifact=None,
                visits=tuple(visits),
                facts=tuple(facts),
                terminal_node=current_id,
                cursor=cursor,
                outcome=outcome,
            )
        except DeclarativeValidationError as exc:
            # Capture cursor at failure point and return failed outcome
            cursor = _build_cursor(current_id)
            error_fact = RunFact(
                fact_id=f"{plan_ref}:{current_id}:validation_error",
                plan_ref=plan_ref,
                kind="run.failed",
                payload={"reason": "validation_error", "error_code": exc.code, "error": str(exc)},
            )
            self._journal.commit_fact(error_fact, plan_ref=plan_ref, node_ref=current_id)
            facts.append(error_fact)
            outcome = DeclarativeRunOutcome(
                kind="failed",
                cursor=cursor,
                stop=_build_stop_decision(should_stop=True),
                error_fact=error_fact,
            )
            return InterpretationResult(
                state=current_state,
                artifact=None,
                visits=tuple(visits),
                facts=tuple(facts),
                terminal_node=current_id,
                cursor=cursor,
                outcome=outcome,
            )
        except Exception as exc:
            # Capture cursor at failure point and return failed outcome
            cursor = _build_cursor(current_id)
            error_fact = RunFact(
                fact_id=f"{plan_ref}:{current_id}:execution_error",
                plan_ref=plan_ref,
                kind="run.failed",
                payload={"reason": "execution_error", "error": str(exc)},
            )
            self._journal.commit_fact(error_fact, plan_ref=plan_ref, node_ref=current_id)
            facts.append(error_fact)
            outcome = DeclarativeRunOutcome(
                kind="failed",
                cursor=cursor,
                stop=_build_stop_decision(should_stop=True),
                error_fact=error_fact,
            )
            return InterpretationResult(
                state=current_state,
                artifact=None,
                visits=tuple(visits),
                facts=tuple(facts),
                terminal_node=current_id,
                cursor=cursor,
                outcome=outcome,
            )

    async def _prepare_input(
        self,
        executable_node: Any,
        context: RestrictedPhaseContext,
        input: PhaseInput,
    ) -> PhaseInput:
        prepared = input
        for contribution in executable_node.contributions:
            if contribution.declaration.role is not ContributionRole.PREPARE:
                continue
            outcome = await contribution.executor.execute(context, prepared)
            self._require_contribution_result(contribution.declaration.executor, outcome)
            if outcome.command_envelope is not None:
                raise DeclarativeValidationError("PG-003", "prepare contribution may not execute an effect")
            if outcome.payload is not None:
                prepared = PhaseInput(artifact=outcome.payload, causation_refs=outcome.evidence_refs)
        return prepared

    async def _apply_post_contributions(
        self,
        executable_node: Any,
        context: RestrictedPhaseContext,
        result: PhaseResult,
        *,
        plan_ref: str,
        node_id: str,
    ) -> tuple[PhaseResult, DeclarativeRunOutcome | None]:
        """Apply post-execution contributions and handle govern verdicts.
        
        Returns:
            Tuple of (updated_result, outcome_if_terminal)
        """
        combined = result
        for contribution in executable_node.contributions:
            role = contribution.declaration.role
            if role is ContributionRole.PREPARE:
                continue
            outcome = await contribution.executor.execute(
                context,
                PhaseInput(artifact=combined.payload, causation_refs=combined.evidence_refs),
            )
            self._require_contribution_result(contribution.declaration.executor, outcome)
            if role is ContributionRole.GOVERN:
                verdict_class = _classify_verdict(outcome.payload)
                if verdict_class == "deny":
                    # Generate control.denied fact
                    deny_fact = RunFact(
                        fact_id=f"{plan_ref}:{node_id}:control_denied",
                        plan_ref=plan_ref,
                        kind="control.denied",
                        payload={
                            "contribution": contribution.declaration.executor,
                            "verdict": verdict_class,
                        },
                    )
                    self._journal.commit_fact(deny_fact, plan_ref=plan_ref, node_ref=node_id)
                    
                    # Build cursor and outcome
                    cursor = PhaseRunCursor(
                        plan_ref=plan_ref,
                        node_id=node_id,
                        visit_counts=tuple(sorted(context.visit_counts.items())),
                        edge_counts=tuple(((k[0], k[1]), v) for k, v in context.edge_counts.items()),
                        artifacts=dict(context.artifacts),
                        causation_refs=combined.evidence_refs,
                        budget_snapshot={"step": context.state.step},
                    )
                    fail_outcome = DeclarativeRunOutcome(
                        kind="failed",
                        cursor=cursor,
                        stop=_build_stop_decision(should_stop=True),
                        error_fact=deny_fact,
                    )
                    return combined, fail_outcome
                elif verdict_class == "pause":
                    # Generate control.paused fact
                    pause_fact = RunFact(
                        fact_id=f"{plan_ref}:{node_id}:control_paused",
                        plan_ref=plan_ref,
                        kind="control.paused",
                        payload={
                            "contribution": contribution.declaration.executor,
                            "verdict": verdict_class,
                        },
                    )
                    self._journal.commit_fact(pause_fact, plan_ref=plan_ref, node_ref=node_id)
                    
                    # Build cursor and outcome
                    cursor = PhaseRunCursor(
                        plan_ref=plan_ref,
                        node_id=node_id,
                        visit_counts=tuple(sorted(context.visit_counts.items())),
                        edge_counts=tuple(((k[0], k[1]), v) for k, v in context.edge_counts.items()),
                        artifacts=dict(context.artifacts),
                        causation_refs=combined.evidence_refs,
                        budget_snapshot={"step": context.state.step},
                    )
                    pause_outcome = DeclarativeRunOutcome(
                        kind="paused",
                        cursor=cursor,
                        stop=_build_stop_decision(should_stop=False),
                        error_fact=pause_fact,
                    )
                    return combined, pause_outcome
                elif verdict_class == "rewrite":
                    # Replace PhaseResult.payload decision_ref and continue
                    if isinstance(outcome.payload, Mapping) and "decision_ref" in outcome.payload:
                        combined = replace(
                            combined,
                            payload=outcome.payload,
                        )
            
            # Handle other contribution roles
            if role in {ContributionRole.TRANSFORM, ContributionRole.FINALIZE} and outcome.payload is not None:
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
        return combined, None

    @staticmethod
    def _require_contribution_result(capability: str, outcome: Any) -> None:
        if not isinstance(outcome, PhaseResult):
            raise DeclarativeValidationError(
                "RT-002", f"contribution returned non-PhaseResult: {capability}"
            )

    def _apply_delta(self, state: Any, delta: RunDelta) -> Any:
        if self._reducer is None:
            return state
        apply = getattr(self._reducer, "apply_delta", None)
        if callable(apply):
            return apply(state, delta)
        folded = getattr(self._reducer, "fold", None)
        if callable(folded):
            return folded(state, delta)
        raise DeclarativeValidationError("RT-001", "configured reducer has no apply_delta/fold operation")

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
        forbidden = prohibited.get(phase, set())
        if result.result_kind in forbidden:
            raise DeclarativeValidationError(
                "RT-002", f"result kind {result.result_kind!r} violates {phase.value} contract"
            )
        if phase is SemanticPhase.ACT and result.command_envelope is not None and not result.command_envelope.decision_ref:
            raise DeclarativeValidationError("PG-002", "act CommandEnvelope has no Decision reference")

    @staticmethod
    def _select_edge(edges: tuple[Any, ...], source: str, result: PhaseResult, artifacts: Mapping[str, Any]) -> Any | None:
        candidates = [edge for edge in edges if edge.source == source]
        for edge in candidates:
            if _evaluate_predicate(edge.when, result=result, artifacts=artifacts):
                return edge
        return None


def _classify_verdict(payload: Any) -> Literal["allow", "deny", "rewrite", "pause", "stop", "defer"]:
    """Classify a control verdict from contribution payload.
    
    Returns one of: allow, deny, rewrite, pause, stop, defer.
    """
    from lca.layer2_runtime.control_runtime import ControlVerdict, ControlVerdictKind
    
    if isinstance(payload, ControlVerdict):
        kind_map = {
            ControlVerdictKind.ALLOW: "allow",
            ControlVerdictKind.DENY: "deny",
            ControlVerdictKind.EXHAUSTED: "stop",
            ControlVerdictKind.STOP: "stop",
            ControlVerdictKind.ASK_HUMAN: "pause",
            ControlVerdictKind.REWRITE: "rewrite",
        }
        return kind_map.get(payload.kind, "allow")
    
    # Fallback for dict payloads
    if isinstance(payload, Mapping):
        verdict = payload.get("verdict")
        if verdict:
            verdict_lower = str(verdict).lower()
            if verdict_lower in {"allow", "allowed", "authorized", "ok"}:
                return "allow"
            if verdict_lower in {"deny", "denied", "rejected"}:
                return "deny"
            if verdict_lower in {"rewrite", "rewritten"}:
                return "rewrite"
            if verdict_lower in {"pause", "ask_human"}:
                return "pause"
            if verdict_lower in {"stop", "halt", "terminate"}:
                return "stop"
            if verdict_lower in {"defer", "deferred"}:
                return "defer"
        if "allowed" in payload:
            return "allow" if bool(payload["allowed"]) else "deny"
    
    # Default to allow for backward compatibility
    return "allow"


def _terminal_result(result: PhaseResult) -> bool:
    payload = result.payload
    if isinstance(payload, Mapping) and "should_stop" in payload:
        return bool(payload["should_stop"])
    if hasattr(payload, "should_stop"):
        return bool(payload.should_stop)
    return True


def _evaluate_predicate(expression: str, *, result: PhaseResult, artifacts: Mapping[str, Any]) -> bool:
    """执行受限且无副作用的 activation/edge DSL。"""
    if expression.strip().lower() == "true":
        return True
    if expression.strip().lower() == "false":
        return False
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise DeclarativeValidationError("PS-001", f"invalid restricted predicate: {expression!r}") from exc
    allowed_roots = {
        "result": result,
        "artifact": artifacts.get("payload"),
        "observation": artifacts.get("observation"),
        "budget": artifacts.get("budget"),
    }
    return bool(_eval_ast(tree.body, allowed_roots))


def _eval_ast(node: ast.AST, roots: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in roots:
            raise DeclarativeValidationError("PS-001", f"predicate root is not allowed: {node.id}")
        return roots[node.id]
    if isinstance(node, ast.Attribute):
        return _read_member(_eval_ast(node.value, roots), node.attr)
    if isinstance(node, ast.Subscript):
        target = _eval_ast(node.value, roots)
        index = _eval_ast(node.slice, roots)
        return target[index]
    if isinstance(node, ast.BoolOp):
        values = [_eval_ast(item, roots) for item in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_ast(node.operand, roots)
    if isinstance(node, ast.Compare):
        left = _eval_ast(node.left, roots)
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval_ast(comparator, roots)
            if isinstance(operator, ast.Eq):
                ok = left == right
            elif isinstance(operator, ast.NotEq):
                ok = left != right
            elif isinstance(operator, ast.In):
                ok = left in right
            elif isinstance(operator, ast.NotIn):
                ok = left not in right
            elif isinstance(operator, ast.Lt):
                ok = left < right
            elif isinstance(operator, ast.LtE):
                ok = left <= right
            elif isinstance(operator, ast.Gt):
                ok = left > right
            elif isinstance(operator, ast.GtE):
                ok = left >= right
            else:
                raise DeclarativeValidationError("PS-001", "unsupported predicate comparison")
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return tuple(_eval_ast(item, roots) for item in node.elts)
    raise DeclarativeValidationError("PS-001", "predicate uses forbidden syntax")


def _read_member(value: Any, key: str) -> Any:
    if key.startswith("_"):  # Prevent private reflection and arbitrary call paths.
        raise DeclarativeValidationError("PS-001", "predicate may not access private attributes")
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key)


__all__ = [
    "GenericPlanInterpreter",
    "InMemoryJournalCommitter",
    "InterpretationResult",
    "PhaseVisit",
    "RestrictedPhaseContext",
]
