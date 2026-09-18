"""V2 driver — directly drives :class:`PlanInterpreter` without v0 GraphAssembler.

ADR-0221 P3 cutover: the v0 ``GraphAssembler`` path is gone. The driver
walks the immutable ``CompiledRunPlan`` through the kernel-native
``PlanInterpreter``, which already wires the NodeExecutor + subgraph
strategies. ``PlanInterpreterAdapter`` (the prior shim) is also gone:
its only remaining job is to register runtime-seam strategies, which
the kernel-side ``DefaultDeclarativeInterpreterFactory`` now exposes
directly through ``PlanInterpreter``.
"""

from __future__ import annotations

from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.policy.stop import StopDecision
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.contracts.protocols.runtime.runtime.composition import ResultFinalizer
from lca.framework.graph.adapter import PhaseRunCursor
from lca.framework.graph.interpreter import InterpretationResult, PlanInterpreter
from lca.runtime.loop.runtime_journal import RuntimeJournal
from lca.runtime.support.checkpoint_resolution import DeclarativeCheckpoint
from lca.runtime.support.runtime_bindings import DeclarativeRuntimeBindings


def _stop_from_interpretation_output(
    output_ports: dict,
    *,
    visits: tuple = (),
) -> StopDecision:
    """Lift graph terminal payload ports into a real ``StopDecision``.

    Prefer an explicit ``StopDecision`` on ``terminal_outcome`` /
    ``stop_payload`` / ``stop_decision``. ``StopPayload`` carries only
    ``reason`` and ``final_output_ref`` (no `should_stop` boolean); the
    presence of ``final_output_ref`` or a non-empty ``reason`` is the
    terminal signal. Recover text from the last respond decision in
    visits when ``final_output_ref`` is a journal pointer.
    """
    from lca.contracts.models.cognition.boundary import StopPayload
    from lca.contracts.models.core.policy.stop import StopDecision, StopReason

    def _resolve_reason(raw_reason: str | None) -> StopReason:
        if not raw_reason:
            return StopReason.CONTINUE
        try:
            return StopReason(raw_reason)
        except ValueError:
            return StopReason.ERROR

    def _from_payload(raw: StopPayload) -> StopDecision:
        final_output = _recover_final_output_text(raw, visits=visits)
        reason = _resolve_reason(raw.reason)
        status = TaskStatus.COMPLETED if reason is StopReason.CONTINUE else TaskStatus.FAILED
        return StopDecision(
            reason=reason,
            final_output=final_output,
            status=status,
        )

    for key in ("terminal_outcome", "stop_payload", "stop_decision", "stop"):
        raw = output_ports.get(key)
        if isinstance(raw, StopDecision):
            return raw
        if isinstance(raw, StopPayload):
            return _from_payload(raw)

    # Scan visits newest-first for a StopDecision / StopPayload in outputs.
    for visit in reversed(tuple(visits) or ()):
        outs = getattr(visit, "outputs", None) or {}
        if not isinstance(outs, dict):
            continue
        for key in ("terminal_outcome", "stop_payload", "stop_decision"):
            raw = outs.get(key)
            if isinstance(raw, StopDecision):
                return raw
            if isinstance(raw, StopPayload):
                return _from_payload(raw)

    return StopDecision(reason=StopReason.ERROR)


def _recover_final_output_text(payload: object, *, visits: tuple = ()) -> str | None:
    """Best-effort text for terminal recording when only a ref is present."""
    direct = getattr(payload, "final_output", None)
    if isinstance(direct, str) and direct.strip():
        return direct
    ref = getattr(payload, "final_output_ref", None)
    if isinstance(ref, str) and ref.strip() and not ref.startswith("mem:") and "\n" in ref:
        # Some paths stash the literal text in the ref field during cutover.
        return ref
    for visit in reversed(tuple(visits) or ()):
        outs = getattr(visit, "outputs", None) or {}
        if not isinstance(outs, dict):
            continue
        decision = outs.get("decision") or outs.get("enforced_decision")
        text = getattr(decision, "response_text", None) if decision is not None else None
        if isinstance(text, str) and text.strip():
            return text
        # Also accept StopDecision nested in outputs.
        nested = outs.get("stop_payload") or outs.get("stop_decision")
        nested_text = getattr(nested, "final_output", None) if nested is not None else None
        if isinstance(nested_text, str) and nested_text.strip():
            return nested_text
    return ref if isinstance(ref, str) and ref.strip() else None


def _pause_from_interrupt(visits: tuple) -> dict | None:
    """Newest-first scan for an ``intervene.resume`` pause signal.

    Returns ``{"node_id", "occurrence", "decision"}`` for the pausing
    visit, or ``None``. Only the documented pause protocol
    (``next_hint == "intervene.resume"``) maps to a paused outcome;
    other ``should_terminate`` terminals (e.g. control "stop"
    verdicts) keep the existing stop-decision path.
    """
    for visit in reversed(tuple(visits) or ()):
        outs = getattr(visit, "outputs", None) or {}
        if not isinstance(outs, dict):
            continue
        for value in outs.values():
            if (
                isinstance(value, RoutingDecision)
                and value.should_terminate
                and value.next_hint == "intervene.resume"
            ):
                node_id = getattr(visit, "node_id", "") or ""
                occurrence = sum(
                    1 for v in (tuple(visits) or ()) if getattr(v, "node_id", None) == node_id
                )
                return {
                    "node_id": node_id,
                    "occurrence": max(occurrence, 1),
                    "decision": outs.get("decision"),
                }
    return None


def _paused_outcome_parts(pause: dict, *, plan_ref: str, visits: tuple) -> tuple:
    """Build the paused ``(stop, cursor, approval_request)`` triple.

    The run stopped at ``intervene.interrupt``; resume re-enters at
    ``intervene.resume`` (outer yaml), so the durable cursor points
    there. ``approval_id`` follows the ``<plan_ref>:<node>:<visit>``
    shape the transport logs on resume.
    """
    from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
        PhaseRunCursor,
    )

    node_id = pause["node_id"] or "intervene.interrupt"
    occurrence = pause["occurrence"] or 1
    approval_id = f"{plan_ref}:{node_id}:{occurrence}"
    questions: list = []
    decision = pause.get("decision")
    tool_calls = getattr(decision, "tool_calls", None) or []
    for call in tool_calls if isinstance(tool_calls, (list, tuple)) else []:
        if getattr(call, "tool_name", None) != "askUserQuestion":
            continue
        arguments = getattr(call, "arguments", None)
        if isinstance(arguments, dict) and isinstance(arguments.get("questions"), list):
            questions = arguments["questions"]
            break
    approval_request: dict[str, object] = {
        "approval_id": approval_id,
        "type": "ask_user_question",
        "questions": questions,
    }
    counts: dict[str, int] = {}
    for visit in tuple(visits) or ():
        name = getattr(visit, "node_id", None)
        if isinstance(name, str) and name:
            counts[name] = counts.get(name, 0) + 1
    # Full-restart resume design: the human answer is folded into state
    # via HumanAnswerResumeInputAdapter, and the graph re-runs from
    # perceive.main. The LLM sees the question-and-answer in full
    # conversational context and reasons about next steps. This matches
    # the industry pattern (LangGraph resume-and-think) and avoids the
    # complexity of mid-graph re-entry with typed port seeding.
    cursor = PhaseRunCursor(
        plan_ref=plan_ref,
        node_id="perceive.main",
        visit_counts=tuple(counts.items()),
        edge_counts=(),
        artifacts={},
        causation_refs=(),
        budget_snapshot={},
    )
    return StopDecision(), cursor, approval_request


class DeclarativeExecution:
    """V2 driver module: ``CompiledRunPlan`` → :class:`InterpretationResult`."""

    def __init__(
        self,
        bindings: DeclarativeRuntimeBindings,
        *,
        journal: RuntimeJournal,
        result_finalizer: ResultFinalizer,
    ) -> None:
        self._bindings = bindings
        self._journal = journal
        self._result_finalizer = result_finalizer

    async def execute(
        self,
        state: AgentState,
        *,
        cursor: PhaseRunCursor | None = None,
    ) -> Result:
        """Run the immutable plan through ``PlanInterpreter``.

        ADR-0221 P3: ``phase_graph`` and ``phase_bindings`` are gone from
        ``CompiledRunPlan``. ``PlanInterpreter`` walks the v2 plan
        directly — no v0 GraphAssembler, no ``MappingRestrictedScope``.
        """
        from lca.framework.graph.lifter import lift_graph_spec
        from lca_kernel.plan.plan_compile import V2ExecutablePlan

        plan = self._bindings.require_executable_plan()
        # ADR-0221 P3: the transport unwraps ``V2ExecutablePlan`` to its
        # inner ``CompiledRunPlan``; recover the v2 graph spec through
        # the ``inner`` handle so the interpreter can still see the
        # bundle nodes/edges.
        inner = getattr(plan, "inner", plan)
        if isinstance(inner, V2ExecutablePlan):
            graph_spec = inner.graph_spec
        elif isinstance(plan, V2ExecutablePlan):
            graph_spec = plan.graph_spec
        else:
            graph_spec = self._load_v2_graph_spec(plan)
        plan_obj = lift_graph_spec(graph_spec)
        interpreter = self._bindings.new_interpreter(journal=self._journal)
        # v2 has no ``resume`` method; seed the traversal manually when
        # a checkpoint cursor is supplied.
        if cursor is None:
            interpretation = await interpreter.run(plan_obj, outer_state=state)
        else:
            from lca.framework.graph.traversal import PlanTraversal

            traversal = PlanTraversal(
                plan=plan_obj,
                current_id=cursor.current_node_id,
            )
            # ADR-0225: resume-path ``traversal.visit`` no longer passes
            # a per-node ``max_visits`` ceiling — the field is gone.
            for node_id in cursor.visited_nodes:
                traversal.visit(node_id=node_id)
            interpretation = await interpreter.run(
                plan_obj,
                outer_state=state,
                traversal=traversal,
            )
        # ADR-0221 P3: ``InterpretationResult`` does not carry the
        # legacy v1 ``state``/``outcome``/``cursor`` shape that the
        # ResultFinalizer still expects. Project terminal ports
        # (especially stop_payload / StopDecision) into that shape —
        # never fabricate an empty StopDecision (that caused COMPLETED
        # tool+respond runs to be misclassified as zero-output FAILED).
        from dataclasses import dataclass as _dc
        from dataclasses import field as _field

        from lca.contracts.models.core.policy.stop import StopReason
        from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
            ExecutionOutcome,
        )
        from lca.framework.graph.adapter import PhaseRunCursor as _PRC

        output_ports = dict(interpretation.output or {})

        pause = _pause_from_interrupt(interpretation.visits)
        if pause is not None:
            stop_decision, pause_cursor, approval_request = _paused_outcome_parts(
                pause,
                plan_ref=self._bindings.plan_ref(),
                visits=interpretation.visits,
            )
        else:
            stop_decision = _stop_from_interpretation_output(
                output_ports, visits=interpretation.visits
            )
            pause_cursor = None
            approval_request = None

        if pause is not None:
            _kind = ExecutionOutcome.PAUSED
            _cursor_value = pause_cursor
        else:
            cursor_obj = interpretation.terminal_node
            _cursor_value = (
                _PRC(current_node_id=cursor_obj, visited_nodes=()) if cursor_obj else None
            )
            if stop_decision.failure is not None or stop_decision.reason is StopReason.ERROR:
                _kind = ExecutionOutcome.FAILED
            else:
                _kind = ExecutionOutcome.COMPLETED

        _stop_value = stop_decision
        _approval_ref = approval_request

        @_dc(frozen=True, slots=True)
        class _OutcomeShim:
            kind: object = _kind
            cursor: object = _cursor_value
            stop: object = _stop_value
            error_fact: object | None = None
            approval_request: dict | None = _field(default_factory=lambda: _approval_ref)

        _outcome = _OutcomeShim()
        _state_ref = state
        _visits_ref = interpretation.visits
        _facts_ref = interpretation.facts
        _terminal_ref = interpretation.terminal_node
        _output_ref = interpretation.output

        @_dc(frozen=True, slots=True)
        class _InterpretShim:
            state: object = _field(default_factory=lambda: _state_ref)
            outcome: object = _field(default=_outcome)
            visits: object = _field(default_factory=lambda: _visits_ref)
            facts: object = _field(default_factory=lambda: _facts_ref)
            terminal_node: object = _field(default_factory=lambda: _terminal_ref)
            output: object = _field(default_factory=lambda: _output_ref)

        return await self._result_finalizer.finalize(
            interpretation=_InterpretShim(),
            plan_ref=self._bindings.plan_ref(),
            journal_sequence=self._journal.sequence,
        )

    def _load_v2_graph_spec(self, plan) -> dict:
        """Walk the resolved bundles, find the first v2 graph spec.

        ADR-0221 P3: bundle yaml carries the v2 graph (``nodes``/``edges``)
        directly; the kernel lifts it without any v1 ``phase_graph``
        reconstruction.
        """
        from pathlib import Path

        import yaml

        bundles = getattr(self._bindings, "bundles", ()) or ()
        for entry in bundles:
            if not isinstance(entry, str):
                continue
            path = Path(entry)
            if not path.exists():
                # Try resolving relative to the profile path.
                profile_path = Path(getattr(plan, "profile_path", ".") or ".")
                candidate = profile_path.parent / entry
                if candidate.exists():
                    path = candidate
                else:
                    continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not (isinstance(data, dict) and ("nodes" in data or "edges" in data)):
                continue
            # ADR-0221 P3 + outer-plan cutover: a phase subgraph bundle has
            # ``id: <phase>.subgraph`` and is meant to be entered through a
            # ``sub_spec_ref`` on the outer plan node, not executed as the
            # outer plan itself. Skip any bundle whose id ends in
            # ``.subgraph`` so the outer plan (id not ending in
            # ``.subgraph``) is selected as the v2 graph spec.
            if str(data.get("id", "")).endswith(".subgraph"):
                continue
            return data
        # No v2 graph found: emit a single empty Plan so the interpreter
        # at least runs end-to-end and the kernel can report the
        # completion back to the caller.
        return {
            "id": getattr(plan, "profile_path", "fallback") or "fallback",
            "nodes": [],
            "edges": [],
        }

    @property
    def plan_ref(self) -> str:
        """返回执行闭包已验证计划的稳定引用。"""
        return self._bindings.plan_ref()


class DeclarativeRuntimeDriver:
    """由不可变运行 binding 构造的 v2 carrier adapter。"""

    def __init__(self, bindings: DeclarativeRuntimeBindings, *, journal: RuntimeJournal) -> None:
        self._bindings = bindings
        self._checkpoint_state_resolver = bindings.new_checkpoint_state_resolver()
        result_finalizer = bindings.new_result_finalizer()
        self._execution = DeclarativeExecution(
            bindings,
            journal=journal,
            result_finalizer=result_finalizer,
        )

    async def run(self, state: AgentState) -> Result:
        """通过单一 v2 Turn module 执行新状态。"""
        return await self._execution.execute(state)

    async def resume(self, checkpoint: DeclarativeCheckpoint) -> Result:
        """先物化 checkpoint 状态，再委托共享 Turn module。"""
        loaded_state = await self._checkpoint_state_resolver.resolve(
            checkpoint,
            expected_plan_ref=self._execution.plan_ref,
        )
        return await self._execution.execute(loaded_state, cursor=checkpoint.cursor)


__all__ = [
    "DeclarativeCheckpoint",
    "DeclarativeExecution",
    "DeclarativeRuntimeDriver",
    "InterpretationResult",
    "PlanInterpreter",
    "RuntimeDriver",
    "TurnExecutor",
]

# ── ADR-0110 D5 / PR-E:「Declarative」前缀公开 re-export ────────────
RuntimeDriver = DeclarativeRuntimeDriver
"""Public alias for ``DeclarativeRuntimeDriver`` (ADR-0110 D5)."""

TurnExecutor = DeclarativeExecution
"""Public alias for ``DeclarativeExecution`` (ADR-0110 D5)."""
