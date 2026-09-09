"""Interpret a compiled declarative phase graph.

The interpreter owns graph traversal, checkpoint/resume entry, and edge
selection. Each phase-node visit is delegated to ``PhaseExecutionTransaction``
and every terminal result is delegated to ``RunOutcomeProjector``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.act.command.envelope import RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    DeclarativeValidationError,
    DeltaReducer,
    EffectDispatcher,
    JournalCommitter,
    PhaseCapabilityReader,
    PhaseEdge,
    PhaseInput,
    PhaseResult,
    PhaseRunCursor,
)
from lca.contracts.protocols.gate.loop_guard import LoopGuardEvaluator
from lca.contracts.protocols.runtime.runtime.lifecycle import (
    RuntimeBudgetSnapshot,
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
    RuntimeLifecyclePublisher,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.compile.assembler.assembler import ExecutablePlan
from lca.harness.declarative.controls.validation import require_valid
from lca.harness.declarative.execute.loop_guard import DeclarativeLoopGuardEvaluator
from lca.harness.declarative.execute.outcome_projection import (
    InterpretationResult,
    PhaseVisit,
    RunOutcomeProjector,
    terminal_result,
)
from lca.harness.declarative.lifecycle.phase_context import RestrictedPhaseContext
from lca.harness.declarative.lifecycle.phase_observation import NullPhaseObserver, PhaseObserver
from lca.harness.graph.predicate import evaluate_restricted_predicate
from lca.harness.graph.traversal import PhaseTraversal
from lca.harness.plan import compiled_run_plan_ref
from lca.loop.transaction import PhaseExecutionTransaction


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


def _extract_run_identity(
    state: object,
    artifacts: Mapping[str, object] | None,
) -> tuple[str, str]:
    """从 ``state`` / ``artifacts`` 派生 ``(run_id, trace_id)``。

    测试环境常用 dict 替代 AgentState;此处宽松接受任何能
    ``getattr`` 出 ``extra`` / ``trace_id`` 的对象。AgentState 的
    顶层字段只有 ``trace_id``;``run_id`` 通过 ``state.extra["run_id"]``
    或 ``artifacts["run_id"]`` 兜底取。
    """
    run_id = ""
    trace_id = ""
    if state is not None:
        trace_id = str(getattr(state, "trace_id", "") or "")
        extra = getattr(state, "extra", None)
        if isinstance(extra, dict):
            run_id = str(extra.get("run_id", "") or "")
    if not run_id and isinstance(artifacts, Mapping):
        run_id = str(artifacts.get("run_id", "") or "")
        if not trace_id:
            trace_id = str(artifacts.get("trace_id", "") or "")
    return run_id, trace_id


# Maximum recursion depth for ``PhaseEdge.subgraph_ref`` traversal.
# A subgraph may not itself reference another subgraph; the runtime
# raises ``PG-005`` if the cap is exceeded. Module-level so the value
# is stable across interpreter instances and is accessible from the
# ``_drive_subgraph`` method body without class-binding gymnastics.
MAX_SUBGRAPH_DEPTH = 4


class GenericPlanInterpreter:
    """Traverse an ``ExecutablePlan`` without reading executor internals.

    Graph concerns stay here: choose the next declared edge and maintain visit
    and edge budgets. Per-phase side effects remain in
    ``PhaseExecutionTransaction``; checkpointing and terminal protocol
    projection remain in ``RunOutcomeProjector``.
    """

    _MAX_SUBGRAPH_DEPTH = MAX_SUBGRAPH_DEPTH

    def __init__(
        self,
        *,
        journal: JournalCommitter | None = None,
        effect_gateway: EffectDispatcher | None = None,
        reducer: DeltaReducer | None = None,
        phase_observer: PhaseObserver | None = None,
        loop_guard_evaluator: LoopGuardEvaluator | None = None,
        lifecycle_publisher: RuntimeLifecyclePublisher | None = None,
        subgraph_resolver: object | None = None,
        subgraph_executable_factory: object | None = None,
    ) -> None:
        self._journal = journal or InMemoryJournalCommitter()
        self._transaction = PhaseExecutionTransaction(
            journal=self._journal,
            effect_gateway=effect_gateway,
            reducer=reducer,
            phase_observer=phase_observer or NullPhaseObserver(),
        )
        # run_id / trace_id 由 _drive 从 AgentState 派生并通过
        # _attach_run_context 在第一次 catch 前注入,确保失败路径上
        # exception 归一化能落 spine。默认空串 → non-run context(boot
        # 测试场景)。
        self._outcomes = RunOutcomeProjector(
            self._journal,
            boundary="declarative.interpreter._drive",
        )
        self._loop_guard_evaluator = loop_guard_evaluator or DeclarativeLoopGuardEvaluator()
        self._lifecycle_publisher = lifecycle_publisher
        # The interpreter knows nothing about plan resolution by default;
        # callers wire a ``SubgraphResolver`` and (optionally) a factory
        # that turns a resolved plan into an ``ExecutablePlan``. The
        # factory is the seam that lets tests substitute hand-built
        # executables without touching the filesystem.
        self._subgraph_resolver = subgraph_resolver
        self._subgraph_executable_factory = subgraph_executable_factory

    async def run(
        self,
        executable: ExecutablePlan,
        *,
        state: AgentState,
        input: PhaseInput | None = None,
        budget: Budget | None = None,
        capabilities: PhaseCapabilityReader | Mapping[str, object] | None = None,
        artifacts: Mapping[str, object] | None = None,
        spec: InfoEdgeSpec | None = None,
    ) -> InterpretationResult:
        """Execute a validated plan from its declared entry node.

        ADR-0210 §6.4: when plan.phase_graph is None, the
        GenericPlanInterpreter falls back to a region-tag-only plan
        synthesized from the spec's region (so the P7 path can run).
        Callers should pass ``spec=`` (an InfoEdgeSpec) when the
        executable doesn't carry one. Without spec, we raise PG-002.
        """
        # P7 region-tag fallback: synthesize a phase graph from the
        # spec's region. This is read-only — plan.phase_graph stays
        # None on the executable (the P7 path); the synthesized plan
        # is local to the drive.
        plan = executable.plan
        if not plan.phase_graph:
            from agent_lab.profile_loader import build_region_only_phase_graph

            if spec is None:
                spec = getattr(executable, "spec", None)
            if spec is None:
                raise DeclarativeValidationError(
                    "PG-002",
                    "phase_graph is None and no spec provided; "
                    "ADR-0210 §6.4 requires spec= for region-tag fallback",
                )
            # Stash the synthesized plan on the executable for the
            # duration of this call; the field stays Optional in the
            # dataclass (we use object.__setattr__ to bypass the frozen
            # pydantic model).
            try:
                object.__setattr__(
                    executable.plan, "phase_graph", build_region_only_phase_graph(spec)
                )
            except Exception:
                # If the plan is frozen, fall back to passing the
                # synthesized graph to _drive explicitly.
                pass

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
        spec: InfoEdgeSpec | None = None,
    ) -> InterpretationResult:
        """Resume from a cursor after verifying that it belongs to this plan.

        ADR-0210 §6.4: P7 region-tag fallback applies on resume as well.
        """
        plan = executable.plan
        if not plan.phase_graph:
            # Apply the same P7 region-tag fallback as run()
            from agent_lab.profile_loader import build_region_only_phase_graph

            if spec is None:
                spec = getattr(executable, "spec", None)
            if spec is None:
                raise DeclarativeValidationError(
                    "PG-002",
                    "phase_graph is None and no spec provided; "
                    "ADR-0210 §6.4 requires spec= for region-tag fallback",
                )
            try:
                object.__setattr__(
                    executable.plan, "phase_graph", build_region_only_phase_graph(spec)
                )
            except Exception:
                pass

        require_valid(plan.validation_report)
        expected_plan_ref = compiled_run_plan_ref(plan)
        # ADR-0068 §决策二 + ADR-0169 D6:cursor.plan_ref 是顶层 accessor
        # (StdLoopCursor.plan_ref property),与 cursor.incarnation.plan_ref
        # 同源。reader 不再需要 ``getattr(cursor, "plan_ref", None)`` —
        # 那是对 cursor 协议的 duck-type 谎言,incarnation 才是 plan_ref
        # 的合法承载位置。
        if cursor.plan_ref != expected_plan_ref:
            raise DeclarativeValidationError(
                "PG-008",
                f"cursor plan_ref {cursor.plan_ref!r} does not match executable plan "
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
        # ADR-0210 §6.4: phase_graph is None is legal (P7 path).
        # run() and resume() already synthesized a region-only plan
        # before reaching here, so the check is just a safety net.
        if not plan.phase_graph:
            raise DeclarativeValidationError(
                "PG-001",
                "plan has no phase graph (run() should have synthesized one "
                "from spec.region; check spec= was passed)",
            )
        require_valid(plan.validation_report)
        graph = plan.phase_graph
        node_by_id = {node.id: node for node in graph.nodes}
        # SSOT 收口(2026-09-03):把 run_id / trace_id 推到 projector,
        # 让 interpreter 失败路径上的异常能归一化到 exception.caught。
        # AgentState 没显式 run_id 顶层字段,从 state.extra / artifacts
        # 兜底取;取不到就退化为 trace_id(空串等价于 non-run context,
        # exception 仍落 spine 但 run_id 字段空)。
        derived_run_id, derived_trace_id = _extract_run_identity(state, artifacts)
        # ADR-0183 §3.9 PR-12:把 derived_trace_id 推到 SpineContext contextvars,
        # 让 wrap_instrument 装饰的 phase emit 走 spine_port_append 时能从
        # contextvars 拿到 trace_id(decorator 不接 trace_id 参数)。
        if derived_trace_id:
            try:
                from lca.infrastructure.observability.spine.context.context import (
                    SpineContext,
                )

                SpineContext.set_trace_id(derived_trace_id)
            except ImportError:
                pass
        if derived_run_id or derived_trace_id:
            self._outcomes = RunOutcomeProjector(
                self._journal,
                run_id=derived_run_id,
                trace_id=derived_trace_id,
                boundary="declarative.interpreter._drive",
            )
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
                if edge.subgraph_ref is not None:
                    # Recurse into the referenced subgraph before
                    # advancing the outer traversal. The subgraph's
                    # terminal PhaseResult is folded into the outer
                    # drive via state merge; visit/edge counts stay
                    # outer-plan-local (different plan_ref).
                    sub_state = await self._drive_subgraph(
                        outer_edge=edge,
                        outer_state=current_state,
                        current_node_id=node.id,
                        depth=1,
                    )
                    current_state = sub_state
                    traversal.advance(
                        edge=edge,
                        payload=transaction.effective_payload,
                        causation_refs=result.evidence_refs,
                    )
                    continue
                traversal.advance(
                    edge=edge,
                    payload=transaction.effective_payload,
                    causation_refs=result.evidence_refs,
                )
        except Exception as exc:
            from lca.contracts.models.core.execution.result import ApprovalPendingError

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

    async def _drive_subgraph(
        self,
        *,
        outer_edge: PhaseEdge,
        outer_state: AgentState,
        current_node_id: str,
        depth: int,
    ) -> AgentState:
        """Recurse into a subgraph plan and return the merged outer state.

        The subgraph is resolved via ``self._subgraph_resolver`` and
        turned into an ``ExecutablePlan`` by
        ``self._subgraph_executable_factory``. Tests substitute a stub
        factory to avoid filesystem I/O. Recursion depth is capped by
        ``_MAX_SUBGRAPH_DEPTH``; exceeding it raises ``PG-005``.
        """
        if depth > MAX_SUBGRAPH_DEPTH:
            raise DeclarativeValidationError(
                "PG-005",
                f"subgraph recursion exceeded {MAX_SUBGRAPH_DEPTH} "
                f"from outer edge {outer_edge.source!r}",
            )
        ref = outer_edge.subgraph_ref
        if ref is None:
            return outer_state
        resolver = self._subgraph_resolver
        if resolver is None:
            raise DeclarativeValidationError(
                "PG-005",
                f"outer edge {outer_edge.source!r} declared subgraph_ref "
                f"but interpreter has no subgraph_resolver wired",
            )
        sub_plan_obj = resolver.resolve(ref.plan_ref)
        if not isinstance(sub_plan_obj, CompiledRunPlan):
            raise DeclarativeValidationError(
                "PG-005",
                f"subgraph_resolver returned non-plan value for "
                f"{ref.plan_ref!r}: {type(sub_plan_obj).__name__}",
            )
        factory = self._subgraph_executable_factory
        if factory is None:
            raise DeclarativeValidationError(
                "PG-005",
                f"interpreter has no subgraph_executable_factory wired for {ref.plan_ref!r}",
            )
        sub_executable = factory(sub_plan_obj)
        sub_traversal = PhaseTraversal.start(
            plan_ref=compiled_run_plan_ref(sub_plan_obj),
            entry_node_id=ref.entry_node,
            artifacts=None,
            input=None,
        )
        sub_result = await self._drive(
            sub_executable,
            state=outer_state,
            input=None,
            budget=None,
            capabilities=None,
            artifacts=None,
            resume_cursor=None,
        )
        # The subgraph's terminal projection carries the merged state
        # because deltas have already been folded into ``outer_state``
        # via the shared ``Reducer`` during recursion. We do NOT import
        # the subgraph's visits/facts into the outer drive (different
        # plan_ref); durability is the caller's job.
        del sub_traversal, current_node_id
        return sub_result.state


__all__ = [
    "GenericPlanInterpreter",
    "InMemoryJournalCommitter",
    "InterpretationResult",
    "PhaseVisit",
    "RestrictedPhaseContext",
]


# ---------------------------------------------------------------------------
# ADR-0210 §6.4 — region-tag fallback when phase_graph is None
# ---------------------------------------------------------------------------


def _resolve_phase_graph(executable, spec=None):
    """Return the CognitivePhaseGraphPlan, synthesizing from region if None.

    Per ADR-0210 §2.1 + §6.4: ``CompiledRunPlan.phase_graph`` is Optional.
    When it's None we build a single-node region-only plan from the
    spec's region label, so the GenericPlanInterpreter can still drive
    one phase per run (the P7 fallback).

    The synthesis lives in agent_lab.profile_loader so the ADR-0210
    test (test_p7_runtime_region_recursion) can verify the closed-set
    rule independent of the interpreter.
    """
    plan = executable.plan
    if plan.phase_graph is not None:
        return plan.phase_graph
    # ADR-0210 §6.4 fallback path
    from agent_lab.profile_loader import build_region_only_phase_graph

    # Prefer the spec attached to the executable if present, else the
    # bare spec passed in.
    target_spec = spec
    if target_spec is None:
        target_spec = getattr(executable, "spec", None)
    if target_spec is None:
        # Nothing to derive from — refuse (we still require a spec).
        raise DeclarativeValidationError(
            "PG-002",
            "phase_graph is None and no spec available to derive region; "
            "either set plan.phase_graph or provide a spec for region-tag "
            "fallback (ADR-0210 §6.4)",
        )
    return build_region_only_phase_graph(target_spec)
