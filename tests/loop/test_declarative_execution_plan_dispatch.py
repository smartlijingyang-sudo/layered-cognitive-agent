"""Dispatch -> assemble -> run seam of ``DeclarativeExecution.execute``.

ADR-0221 P3 retired the v0 ``GraphAssembler``: ``execute()`` now resolves the
runnable v2 graph from the plan *before* the interpreter ever runs, reading
the spec off three possible plan shapes:

1. transport-unwrapped wrapper whose ``.inner`` is a ``V2ExecutablePlan``
   (recover ``graph_spec`` through the ``inner`` handle);
2. a ``V2ExecutablePlan`` itself (read ``graph_spec`` off the plan);
3. a plain plan (recover the v2 graph spec from bundle yaml, skipping
   ``*.subgraph`` bundles — ``_load_v2_graph_spec``).

Plus two dispatch-honesty behaviors:

4. resume: a checkpoint ``cursor`` seeds the traversal's visited nodes
   before ``interpreter.run`` (ADR-0225: no per-node visit cap anymore);
5. a non-shape interpreter result fails loud with ``TypeError`` instead of
   dying later with ``AttributeError``.

Interpretation doubles are structural fakes, not bare ``MagicMock``: the
``isinstance(interpretation, _InterpretationLike)`` guard is a
``runtime_checkable`` Protocol whose data-member check resolves through
``inspect.getattr_static`` on 3.12, which never sees ``MagicMock``
attributes — a bare mock would pass/fail the guard for the wrong reason.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.framework.graph.adapter import PhaseRunCursor
from lca.harness.declarative.lifecycle.phase_observation import NullPhaseObserver
from lca.loop.driver import DeclarativeExecution
from lca.runtime.support.runtime_bindings import (
    DeclarativeRuntimeBindings,
    RuntimePhaseCapabilities,
)
from lca_kernel.plan.plan_compile import V2ExecutablePlan


def _spec(*node_ids: str) -> dict:
    """Minimal liftable v2 graph spec: one entry, all nodes terminal."""
    return {
        "id": "dispatch-seam",
        "entry": node_ids[0],
        "nodes": [{"id": nid, "binding": "node_executor", "terminal": True} for nid in node_ids],
        "edges": [],
    }


def _v2_plan(graph_spec: dict) -> V2ExecutablePlan:
    """Real ``V2ExecutablePlan`` without paying for the parent plan fields.

    ``execute()`` only ever reads ``inner``/``graph_spec`` off the wrapper
    (plus ``isinstance``), so the inherited ``CompiledRunPlan`` fields are
    irrelevant on this seam and skipped deliberately.
    """
    plan = V2ExecutablePlan.__new__(V2ExecutablePlan)
    object.__setattr__(plan, "inner", None)
    object.__setattr__(plan, "graph_spec", graph_spec)
    return plan


class _FakeInterpretation:
    """Structural fake satisfying the driver's ``_InterpretationLike`` shape."""

    def __init__(self, terminal_node: str = "node-a") -> None:
        self.output = {}
        self.visits = ()
        self.facts = ()
        self.terminal_node = terminal_node


class _FakeInterpreter:
    def __init__(self, result: object) -> None:
        self._result = result
        self.run_calls: list[dict] = []

    async def run(self, plan_obj, *, outer_state=None, traversal=None):
        self.run_calls.append(
            {"plan": plan_obj, "outer_state": outer_state, "traversal": traversal}
        )
        return self._result


class _FakeInterpreterFactory:
    def __init__(self, interpreter: _FakeInterpreter) -> None:
        self._interpreter = interpreter
        self.create_kwargs: dict | None = None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return self._interpreter


class _FakeFinalizer:
    def __init__(self) -> None:
        self.finalize_kwargs: dict | None = None

    async def finalize(self, *, interpretation, plan_ref, journal_sequence):
        self.finalize_kwargs = {
            "interpretation": interpretation,
            "plan_ref": plan_ref,
            "journal_sequence": journal_sequence,
        }
        return "final-result"


class _FakeJournal:
    sequence = 7


def _state() -> AgentState:
    return AgentState(trace_id="trace-dispatch-seam", task="dispatch seam", budget=Budget())


def _make_bindings(plan, interpreter_factory) -> DeclarativeRuntimeBindings:
    return DeclarativeRuntimeBindings.assemble(
        plan=plan,
        node_executors={"node-a": object()},
        capabilities=RuntimePhaseCapabilities(
            {
                "brain": MagicMock(),
                "body": MagicMock(),
                "memory": MagicMock(),
                "perceive_hub": MagicMock(),
                "stop_policy": MagicMock(),
            }
        ),
        reducer=MagicMock(),
        hooks=MagicMock(),
        effect_handler_registry=MagicMock(),
        delta_handler_registry=MagicMock(),
        artifact_closure=MagicMock(),
        idempotency_store=MagicMock(),
        resume_input_adapter=MagicMock(),
        state_store=MagicMock(),
        effect_dispatcher_factory=MagicMock(),
        delta_reducer_factory=MagicMock(),
        journal_factory=MagicMock(),
        interpreter_factory=interpreter_factory,
        checkpoint_state_resolver_factory=MagicMock(),
        result_finalizer_factory=MagicMock(),
        phase_observer=NullPhaseObserver(),
    )


def _make_execution(plan, interpreter, monkeypatch):
    factory = _FakeInterpreterFactory(interpreter)
    bindings = _make_bindings(plan, factory)
    # plan_ref hashing is pinned elsewhere; the seam under test is
    # plan -> graph_spec -> interpreter dispatch.
    monkeypatch.setattr(DeclarativeRuntimeBindings, "plan_ref", lambda self: "plan-ref-stub")
    journal = _FakeJournal()
    finalizer = _FakeFinalizer()
    execution = DeclarativeExecution(bindings, journal=journal, result_finalizer=finalizer)
    return execution, factory, journal, finalizer


async def test_execute_recovers_graph_spec_through_inner_handle(monkeypatch):
    """Transport-unwrapped plan: ``.inner`` is the V2ExecutablePlan (ADR-0221 P3)."""
    interpreter = _FakeInterpreter(_FakeInterpretation())
    plan = SimpleNamespace(inner=_v2_plan(_spec("node-a")))
    execution, factory, journal, finalizer = _make_execution(plan, interpreter, monkeypatch)

    result = await execution.execute(_state())

    assert result == "final-result"
    plan_obj = interpreter.run_calls[0]["plan"]
    assert [n.id for n in plan_obj.nodes] == ["node-a"]
    # the injected journal is dispatched through to the interpreter factory
    assert factory.create_kwargs is not None
    assert factory.create_kwargs["journal"] is journal
    assert finalizer.finalize_kwargs["plan_ref"] == "plan-ref-stub"
    assert finalizer.finalize_kwargs["journal_sequence"] == 7


async def test_execute_reads_graph_spec_from_direct_v2_plan(monkeypatch):
    """Plan IS the V2ExecutablePlan: read graph_spec off the plan itself."""
    interpreter = _FakeInterpreter(_FakeInterpretation(terminal_node="node-b"))
    plan = _v2_plan(_spec("node-b"))
    execution, _, _, _ = _make_execution(plan, interpreter, monkeypatch)

    await execution.execute(_state())

    plan_obj = interpreter.run_calls[0]["plan"]
    assert [n.id for n in plan_obj.nodes] == ["node-b"]


async def test_execute_skips_subgraph_bundles_when_recovering_spec(monkeypatch, tmp_path):
    """Plain plan: first non-``*.subgraph`` bundle yaml wins (ADR-0221 P3)."""
    sub = tmp_path / "phase.subgraph.yaml"
    sub.write_text(
        yaml.safe_dump(
            {
                "id": "phase.subgraph",
                "entry": "node-sub",
                "nodes": [
                    {
                        "id": "node-sub",
                        "binding": "node_executor",
                        "terminal": True,
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    main = tmp_path / "main.yaml"
    main.write_text(
        yaml.safe_dump(
            {
                "id": "main-plan",
                "entry": "node-main",
                "nodes": [
                    {
                        "id": "node-main",
                        "binding": "node_executor",
                        "terminal": True,
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(DeclarativeRuntimeBindings, "bundles", [str(sub), str(main)], raising=False)
    interpreter = _FakeInterpreter(_FakeInterpretation(terminal_node="node-main"))
    execution, _, _, _ = _make_execution(SimpleNamespace(), interpreter, monkeypatch)

    await execution.execute(_state())

    plan_obj = interpreter.run_calls[0]["plan"]
    assert [n.id for n in plan_obj.nodes] == ["node-main"]


async def test_execute_seeds_traversal_visited_nodes_from_cursor(monkeypatch):
    """Resume: checkpoint cursor seeds visited nodes before interpreter.run."""
    interpreter = _FakeInterpreter(_FakeInterpretation(terminal_node="node-b"))
    plan = _v2_plan(_spec("node-a", "node-b"))
    execution, _, _, _ = _make_execution(plan, interpreter, monkeypatch)
    cursor = PhaseRunCursor(current_node_id="node-b", visited_nodes=("node-a",))

    await execution.execute(_state(), cursor=cursor)

    traversal = interpreter.run_calls[0]["traversal"]
    assert traversal is not None
    assert traversal.current_id == "node-b"
    assert traversal.visit_counts == {"node-a": 1}


async def test_execute_raises_typeerror_for_non_shape_interpreter_result(monkeypatch):
    """Honesty guard: non-shape result fails loud, not AttributeError later."""
    interpreter = _FakeInterpreter(object())  # no output/visits/facts/terminal_node
    plan = _v2_plan(_spec("node-a"))
    execution, _, _, _ = _make_execution(plan, interpreter, monkeypatch)

    with pytest.raises(TypeError, match="requires a result with output/visits/facts/terminal_node"):
        await execution.execute(_state())
