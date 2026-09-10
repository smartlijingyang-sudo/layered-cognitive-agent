"""Cordis-registered declarative phase-graph interpreter (think-subgraph engine).

This module hosts the ``GenericPlanInterpreter`` class (migrated from
``lca.harness.graph.execute.interpreter``) together with its
``@plugin`` registration.  The interpreter is registered as a Cordis
DRIVER plugin; every capability it needs is injected through
``ctx.inject(...)`` at ``setup`` time instead of being passed via
``__init__`` kwargs.  The old import path remains a re-export shim for
tests and downstream callers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
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
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.act.command.envelope import RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    JournalCommitter,
    PhaseResult,
    PhaseRunCursor,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    DeclarativeValidationError,
    DeltaReducer,
    EffectDispatcher,
    PhaseCapabilityReader,
    PhaseEdge,
    PhaseInput,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.gate.loop_guard import LoopGuardEvaluator
from lca.contracts.protocols.runtime.runtime.lifecycle import (
    RuntimeBudgetSnapshot,
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
    RuntimeLifecyclePublisher,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.framework.subgraph.plugins.channel import PhaseOutput
from lca.harness.declarative.compile.assembler.assembler import (
    ExecutablePlan,
    RestrictedScope,
)
from lca.harness.declarative.controls.validation import require_valid
from lca.harness.declarative.execute.loop_guard import DeclarativeLoopGuardEvaluator
from lca.harness.declarative.execute.outcome_projection import (
    InterpretationResult,
    PhaseVisit,
    RunOutcomeProjector,
    terminal_result,
)
from lca.harness.declarative.lifecycle.phase_observation import NullPhaseObserver, PhaseObserver
from lca.harness.graph.execute.hook_seam import (
    NullSubgraphHookEmitter,
    SubgraphHookContext,
    SubgraphHookEmitter,
    SubgraphHookEvent,
)
from lca.harness.graph.predicate import evaluate_restricted_predicate
from lca.harness.graph.traversal import PhaseTraversal
from lca.harness.plan import compiled_run_plan_ref
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
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
    """Derive ``(run_id, trace_id)`` from ``state`` / ``artifacts`` for SSOT closure."""

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


MAX_SUBGRAPH_DEPTH = 4


if TYPE_CHECKING:
    from agent_lab.graph.spec import InfoEdgeSpec


class GenericPlanInterpreter:
    """Traverse an ``ExecutablePlan`` without reading executor internals.

    Graph concerns stay here: choose the next declared edge and maintain visit
    and edge budgets. Per-phase side effects remain in
    ``PhaseExecutionTransaction``; checkpointing and terminal protocol
    projection remain in ``RunOutcomeProjector``.

    Per review 2026-09-10 §13.10 / R6: every capability this interpreter needs
    is injected through Cordis at ``setup`` time (see the ``setup`` plugin
    entry below) and stored on the instance; no capability is passed through
    ``__init__`` for tests either — the dataclass-style defaults remain for
    legacy callers that construct the interpreter directly.
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
        subgraph_hook_emitter: SubgraphHookEmitter | None = None,
    ) -> None:
        self._journal = journal or InMemoryJournalCommitter()
        self._transaction = PhaseExecutionTransaction(
            journal=self._journal,
            effect_gateway=effect_gateway,
            reducer=reducer,
            phase_observer=phase_observer or NullPhaseObserver(),
        )
        self._outcomes = RunOutcomeProjector(
            self._journal,
            boundary="declarative.interpreter._drive",
        )
        self._loop_guard_evaluator = loop_guard_evaluator or DeclarativeLoopGuardEvaluator()
        self._lifecycle_publisher = lifecycle_publisher
        self._subgraph_hook_emitter: SubgraphHookEmitter = (
            subgraph_hook_emitter or NullSubgraphHookEmitter()
        )
        # Cordis-injected think-subgraph single-engine seams.  These are
        # ``None`` for legacy direct constructors; the plugin ``setup``
        # below wires them through ``ctx.inject(...)`` so the think
        # subgraph branch in ``_drive`` can delegate to the v2 driver.
        self._subgraph_runner: object | None = None
        self._subgraph_runtime: object | None = None
        self._channel_factory: object | None = None
        # ADR-0219 §10.11 item (4): observer port on the interpreter. Stored
        # here so the Default factory (which constructs SubgraphRunner
        # directly) can pick them up via ``self._observers``.
        self._observers: tuple = ()
        # Set for the duration of ``_drive`` so nested subgraph recursion
        # can reuse the outer run's phase capabilities (brain/body/etc.).
        self._active_capabilities: PhaseCapabilityReader | Mapping[str, object] | None = None

    def bind_cordis_seams(
        self,
        *,
        subgraph_runner: object | None = None,
        subgraph_runtime: object | None = None,
        channel_factory: object | None = None,
        observers: tuple = (),
    ) -> None:
        """Attach Cordis-injected think-subgraph seams.

        Called by the ``setup`` plugin below.  Kept separate from
        ``__init__`` so legacy direct constructors continue to work
        without any Cordis involvement.

        All kwargs are optional with ``()`` / ``None`` defaults. Partial
        bind is allowed — caller may inject only the seam they need; the
        interpreter's main loop fail-louds if a sub_spec_ref node fires
        and the corresponding seam is ``None``.

        ADR-0219 §10.11 item (4): ``observers`` is forwarded to the
        ``SubgraphRunner`` constructed by the Default factory so the
        inner driver emits ``phase_graph.node.start/end`` for each node
        execution into the observer funnel.
        """
        if subgraph_runner is not None:
            self._subgraph_runner = subgraph_runner
        if subgraph_runtime is not None:
            self._subgraph_runtime = subgraph_runtime
        if channel_factory is not None:
            self._channel_factory = channel_factory
        self._observers = tuple(observers)

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
            try:
                object.__setattr__(
                    executable.plan, "phase_graph", build_region_only_phase_graph(spec)
                )
            except Exception:
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
        """Resume from a cursor after verifying that it belongs to this plan."""

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
            try:
                object.__setattr__(
                    executable.plan, "phase_graph", build_region_only_phase_graph(spec)
                )
            except Exception:
                pass

        require_valid(plan.validation_report)
        expected_plan_ref = compiled_run_plan_ref(plan)
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
        allow_natural_exit: bool = False,
    ) -> InterpretationResult:
        plan = executable.plan
        if not plan.phase_graph:
            raise DeclarativeValidationError(
                "PG-001",
                "plan has no phase graph (run() should have synthesized one "
                "from spec.region; check spec= was passed)",
            )
        require_valid(plan.validation_report)
        graph = plan.phase_graph
        node_by_id = {node.id: node for node in graph.nodes}
        derived_run_id, derived_trace_id = _extract_run_identity(state, artifacts)
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
        previous_capabilities = self._active_capabilities
        self._active_capabilities = capabilities

        try:
            while True:
                current_id = traversal.current_node_id
                node = node_by_id.get(current_id)
                # Plan §13.11: sub_spec_ref 节点不进 assembler.executable.nodes
                # (无 phase executor), interpreter 走 sub_runner 委托;
                # 其他节点仍要求 executable_node 已装配。
                executable_node = (
                    executable.nodes.get(current_id)
                    if node is None or node.sub_spec_ref is None
                    else None
                )
                if node is None or (executable_node is None and node.sub_spec_ref is None):
                    raise DeclarativeValidationError(
                        "PG-001", f"unassembled phase node: {current_id}"
                    )
                visit_count = traversal.visit(node_id=node.id, max_visits=node.max_visits)
                # Per review 2026-09-10 §13.10 / R6: think subgraph nodes
                # declare ``sub_spec_ref``; the outer drive delegates the
                # whole subgraph to ``SubgraphRunner`` (Cordis-injected
                # single-engine seam) and folds its PhaseOutput back into
                # the outer channel before advancing.
                if node.sub_spec_ref is not None:
                    # Per plan §13.10/R6: think subgraph 走 Cordis-injected SubgraphRunner
                    # 单引擎 seam。必须通过 bind_cordis_seams 注入;缺失直接 fail-loud
                    # (不允许 silent fallback)。
                    if self._subgraph_runner is None or self._channel_factory is None:
                        raise DeclarativeValidationError(
                            "PG-005",
                            f"think subgraph node={node.id!r} has sub_spec_ref "
                            f"but interpreter has no Cordis-injected "
                            f"subgraph_runner/channel_factory; "
                            f"call bind_cordis_seams() first",
                        )
                    sub_runner = self._subgraph_runner
                    channel = self._channel_factory()
                    sub_state, output = await sub_runner.run(
                        ref=node.sub_spec_ref,
                        outer_state=current_state,
                        channel=channel,
                    )
                    channel.absorb(output)
                    current_state = sub_state
                    virtual_result = self._fold_subgraph_output(output)
                    edge = self._select_edge(
                        graph.edges,
                        node.id,
                        virtual_result,
                        traversal.artifacts,
                        current_state,
                    )
                    if edge is None:
                        if allow_natural_exit:
                            cursor = traversal.checkpoint(
                                node_id=node.id,
                                causation_refs=(),
                                state_step=getattr(current_state, "step", 0),
                            )
                            return InterpretationResult(
                                state=current_state,
                                artifact=None,
                                visits=tuple(visits),
                                facts=tuple(facts),
                                terminal_node=node.id,
                                cursor=cursor,
                                outcome=None,
                            )
                        raise DeclarativeValidationError(
                            "PG-006",
                            f"no validated next edge from node: {node.id} after sub_spec",
                        )
                    visits.append(
                        PhaseVisit(node.id, node.semantic_phase, virtual_result.result_kind, edge.target)
                    )
                    payload = virtual_result.payload
                    traversal.record_result(
                        semantic_phase=node.semantic_phase,
                        result=virtual_result,
                        effect_output=payload,
                    )
                    traversal.advance(
                        edge=edge,
                        payload=payload,
                        causation_refs=(),
                    )
                    continue
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
                    if allow_natural_exit:
                        cursor = traversal.checkpoint(
                            node_id=node.id,
                            causation_refs=result.evidence_refs,
                            state_step=getattr(current_state, "step", 0),
                        )
                        return InterpretationResult(
                            state=current_state,
                            artifact=transaction.effective_payload,
                            visits=tuple(visits),
                            facts=tuple(facts),
                            terminal_node=node.id,
                            cursor=cursor,
                            outcome=None,
                        )
                    raise DeclarativeValidationError(
                        "PG-006", f"no validated next edge from node: {node.id}"
                    )
                visits.append(
                    PhaseVisit(node.id, node.semantic_phase, result.result_kind, edge.target)
                )
                if edge.subgraph_ref is not None:
                    sub_state = await self._drive_subgraph_ref(
                        ref=edge.subgraph_ref,
                        outer_state=current_state,
                        current_node_id=node.id,
                        depth=1,
                        edge_id=edge.source,
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
        finally:
            self._active_capabilities = previous_capabilities

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
        """Choose the first matching edge admitted by its optional loop guard."""

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

    @staticmethod
    def _emit_subgraph_hook(emitter: SubgraphHookEmitter, ctx: SubgraphHookContext) -> None:
        """Contain emitter failures so observation never breaks the drive."""

        try:
            emitter.emit(ctx)
        except Exception as exc:  # containment boundary
            import logging

            logging.getLogger(__name__).debug("subgraph hook emitter raised: %s", exc)

    @staticmethod
    def _fold_subgraph_output(output: PhaseOutput) -> PhaseResult:
        """Fold a subgraph's typed PhaseOutput into a single PhaseResult.

        The subgraph's external contract is ``output.decision``; the other
        fields (observation / reflection / response) are consumed by
        other phases, not the outer interpreter.
        """
        return PhaseResult(
            result_kind="decision",
            payload=output.decision,
        )

    async def _drive_subgraph(
        self,
        *,
        outer_edge: PhaseEdge,
        outer_state: AgentState,
        current_node_id: str,
        depth: int,
    ) -> AgentState:
        """Edge-level subgraph recursion shell."""

        ref = outer_edge.subgraph_ref
        if ref is None:
            return outer_state
        return await self._drive_subgraph_ref(
            ref=ref,
            outer_state=outer_state,
            current_node_id=current_node_id,
            depth=depth,
            edge_id=outer_edge.source,
        )

    async def _drive_subgraph_ref(
        self,
        *,
        ref: SubgraphReference,
        outer_state: AgentState,
        current_node_id: str,
        depth: int,
        edge_id: str,
    ) -> AgentState:
        """Recurse into a subgraph plan and return the merged outer state.

        ADR-0219 §3 + §6: **single seam** for subgraph recursion. The
        Cordis-injected ``SubgraphRunner`` owns plan resolution, cycle
        and depth guards, and the inner node loop (via
        :class:`NodeGraphDriver`). The v1 ``GraphAssembler + inner
        _drive`` path is removed (legacy deleted per ADR-0219 §10.5
        reject); the runner is the only path.
        """

        if depth > MAX_SUBGRAPH_DEPTH:
            raise DeclarativeValidationError(
                "PG-005",
                f"subgraph recursion exceeded {MAX_SUBGRAPH_DEPTH} from outer seam {edge_id!r}",
            )

        sub_runner = self._subgraph_runner
        channel_factory = self._channel_factory
        if sub_runner is None or channel_factory is None:
            raise DeclarativeValidationError(
                "PG-005",
                f"subgraph_ref {ref.binding_edge!r} declared but interpreter "
                f"has no Cordis-injected subgraph_runner/channel_factory; "
                f"call bind_cordis_seams() first",
            )

        emitter = self._subgraph_hook_emitter
        self._emit_subgraph_hook(
            emitter,
            SubgraphHookContext(
                event=SubgraphHookEvent.SUBGRAPH_ENTER,
                plan_ref=ref.plan_ref,
                entry_node=ref.entry_node,
                binding_edge=ref.binding_edge,
                depth=depth,
                parent_path="",
                node_id=current_node_id,
                edge_id=edge_id,
                outcome="in_progress",
            ),
        )

        result_state: AgentState = outer_state
        outcome = "success"
        error = ""
        try:
            channel = channel_factory()
            sub_state, output = await sub_runner.run(
                ref=ref,
                outer_state=outer_state,
                channel=channel,
            )
            channel.absorb(output)
            result_state = sub_state
        except DeclarativeValidationError as exc:
            outcome = "validation_error"
            error = f"{exc.code}: {exc}"
            raise
        except Exception as exc:
            outcome = "execution_error"
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._emit_subgraph_hook(
                emitter,
                SubgraphHookContext(
                    event=SubgraphHookEvent.SUBGRAPH_EXIT,
                    plan_ref=ref.plan_ref,
                    entry_node=ref.entry_node,
                    binding_edge=ref.binding_edge,
                    depth=depth,
                    parent_path="",
                    node_id=current_node_id,
                    edge_id=edge_id,
                    outcome=outcome,
                    error=error,
                ),
            )
        return result_state


# ---------------------------------------------------------------------------
# ADR-0210 §6.4 — region-tag fallback when phase_graph is None
# ---------------------------------------------------------------------------


def _resolve_phase_graph(executable: object, spec: object | None = None) -> object:
    """Return the CognitivePhaseGraphPlan, synthesizing from region if None.

    Per ADR-0210 §2.1 + §6.4: ``CompiledRunPlan.phase_graph`` is Optional.
    When it's None we build a single-node region-only plan from the
    spec's region label, so the GenericPlanInterpreter can still drive
    one phase per run (the P7 fallback).

    The synthesis lives in :mod:`agent_lab.profile_loader` so the ADR-0210
    test (``test_p7_runtime_region_recursion``) can verify the closed-set
    rule independent of the interpreter.
    """
    plan = getattr(executable, "plan", None)
    existing_graph = getattr(plan, "phase_graph", None)
    if existing_graph is not None:
        return existing_graph
    from agent_lab.profile_loader import build_region_only_phase_graph

    target_spec = spec
    if target_spec is None:
        target_spec = getattr(executable, "spec", None)
    if target_spec is None:
        raise DeclarativeValidationError(
            "PG-002",
            "phase_graph is None and no spec available to derive region; "
            "either set plan.phase_graph or provide a spec for region-tag "
            "fallback (ADR-0210 §6.4)",
        )
    return build_region_only_phase_graph(target_spec)


class Config(BaseModel):
    """The declarative interpreter plugin has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


@plugin(
    id="declarative.interpreter",
    requires=(
        "subgraph_runner",
        "subgraph_runtime",
        "phase_output_channel_factory",
        "loop_guard_evaluator",
    ),
    provides=["declarative_interpreter"],
    layer="L2",
    effects="none",
    kind=PluginKind.DRIVER,
    description=(
        "Provide the default declarative phase-graph interpreter, with all of "
        "its capability seams injected through Cordis (think-subgraph single "
        "engine, batch 2)."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "declarative.interpreter.checked",
                "declarative.interpreter.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(
            "plugin.serve",
            "journal_committer",
            "effect_gateway",
            "delta_reducer",
            "phase_observer",
            "subgraph_runner",
            "subgraph_runtime",
            "phase_output_channel_factory",
            "loop_guard_evaluator",
            "runtime_lifecycle_publisher",
        ),
        emits=("plugin.served", "declarative.interpreter.executed"),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Construct the interpreter instance with Cordis-injected capability seams."""

    del config
    loop_guard_evaluator = ctx.require("loop_guard_evaluator")
    subgraph_runner = ctx.require("subgraph_runner")
    subgraph_runtime = ctx.require("subgraph_runtime")
    channel_factory = ctx.require("phase_output_channel_factory")
    # ADR-0219 §10.11 item (4): observer port from Cordis. Cordis-boot
    # may pass an empty tuple; the Default factory injects the
    # Session.append closure directly via its own construction path.
    observers: tuple = ()
    try:
        observers = tuple(ctx.require("subgraph_observers"))
    except Exception:
        observers = ()

    # journal / effect_gateway / reducer / phase_observer / lifecycle_publisher
    # are wired by ``runtime_bindings.assemble`` from the *_factory
    # capabilities (not Cordis-bound). Pass None placeholders; the
    # interpreter accepts the binding-level replacements via its
    # generic PlanInput once the runtime_bindings construct it.
    interpreter = GenericPlanInterpreter(
        journal=None,
        effect_gateway=None,
        reducer=None,
        phase_observer=None,
        loop_guard_evaluator=loop_guard_evaluator,
        lifecycle_publisher=None,
    )
    interpreter.bind_cordis_seams(
        subgraph_runner=subgraph_runner,
        subgraph_runtime=subgraph_runtime,
        channel_factory=channel_factory,
        observers=observers,
    )
    ctx.provide("declarative_interpreter", interpreter)


__all__ = [
    "MAX_SUBGRAPH_DEPTH",
    "Config",
    "GenericPlanInterpreter",
    "InMemoryJournalCommitter",
    "setup",
]
