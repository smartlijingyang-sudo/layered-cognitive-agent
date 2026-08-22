"""ADR-0075 的通用声明式计划解释器。"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from lca.contracts.protocols.command_envelope import RunDelta, RunFact
from lca.contracts.protocols.declarative_phase_graph import (
    ContributionRole,
    DeclarativeValidationError,
    EffectGateway,
    JournalCommitter,
    PhaseContext,
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.plan import compiled_run_plan_ref
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
        plan = executable.plan
        if not plan.phase_graph:
            raise DeclarativeValidationError("PG-001", "plan has no phase graph")
        plan.validation_report.require_valid()
        graph = plan.phase_graph
        node_by_id = {node.id: node for node in graph.nodes}
        current_id = graph.entry
        current_input = input or PhaseInput()
        current_state = state
        visit_counts: dict[str, int] = {}
        edge_counts: dict[tuple[str, str], int] = {}
        facts: list[RunFact] = []
        visits: list[PhaseVisit] = []
        artifact_map = dict(artifacts or {})
        plan_ref = compiled_run_plan_ref(plan)

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
            result = await self._apply_post_contributions(
                executable_node,
                context,
                result,
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
                return InterpretationResult(
                    state=current_state,
                    artifact=effective_payload,
                    visits=tuple(visits),
                    facts=tuple(facts),
                    terminal_node=node.id,
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
    ) -> PhaseResult:
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
            if role is ContributionRole.GOVERN and not _verdict_allows(outcome.payload):
                raise DeclarativeValidationError(
                    "RT-002",
                    f"govern contribution denied phase execution: {contribution.declaration.executor}",
                )
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
        return combined

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


def _verdict_allows(payload: Any) -> bool:
    if isinstance(payload, Mapping):
        if "allowed" in payload:
            return bool(payload["allowed"])
        if "verdict" in payload:
            return str(payload["verdict"]).lower() in {"allow", "allowed", "authorized", "ok"}
    if isinstance(payload, bool):
        return payload
    return True


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
