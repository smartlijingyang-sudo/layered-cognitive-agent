"""Integration: runtime_bindings._build_graph_observer wires active spine.

Verifies the production wiring seam: when the process-local spine
accessor is installed, ``DeclarativeRuntimeBindings._build_graph_observer``
returns a :class:`SpineGraphObserver` whose emit callable routes
observations to the same spine the rest of the system uses. When
no spine is active, it returns ``None`` and ``PlanInterpreterAdapter``
falls back to its NullGraphObserver (default).

Tests pin only the wiring contract, not the full boot path. The
file deliberately avoids touching the existing runtime scenarios
so it stays a focused regression lock.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lca.framework.graph.observation import (
    KIND_VISIT_START,
    GraphObservation,
    NullGraphObserver,
)
from lca.framework.graph.observer_impls import SpineGraphObserver
from lca.harness.declarative.compile.instrument.wrap import (
    set_active_spine_accessor,
)


def _minimal_bindings() -> object:
    """Build a DeclarativeRuntimeBindings instance with empty fields.

    ``_build_graph_observer`` only reads the process-local spine
    accessor; no field of the bindings is touched. ``assemble``
    lets us skip the full dependency closure while still passing
    the frozen-dataclass init gate.
    """
    from lca.runtime.support.runtime_bindings import DeclarativeRuntimeBindings

    return DeclarativeRuntimeBindings.assemble(
        plan=None,
        node_executors={},
        capabilities=MagicMock(name="capabilities"),
        reducer=MagicMock(name="reducer"),
        hooks=MagicMock(name="hooks"),
        effect_handler_registry=MagicMock(name="effect_handlers"),
        delta_handler_registry=MagicMock(name="delta_handlers"),
        artifact_closure=MagicMock(name="artifact_closure"),
        idempotency_store=MagicMock(name="idempotency"),
        resume_input_adapter=MagicMock(name="resume"),
        state_store=MagicMock(name="state_store"),
        effect_dispatcher_factory=MagicMock(name="ed_factory"),
        delta_reducer_factory=MagicMock(name="dr_factory"),
        journal_factory=MagicMock(name="journal_factory"),
        interpreter_factory=MagicMock(name="interpreter_factory"),
        checkpoint_state_resolver_factory=MagicMock(name="ck_factory"),
        result_finalizer_factory=MagicMock(name="rf_factory"),
        phase_observer=MagicMock(name="phase_observer"),
    )


def test_build_graph_observer_returns_none_when_no_spine_active() -> None:
    """Without an active spine the wiring must not invent one."""
    previous = set_active_spine_accessor(None)
    try:
        bindings = _minimal_bindings()
        assert bindings._build_graph_observer() is None
    finally:
        set_active_spine_accessor(previous)


def test_build_graph_observer_uses_active_spine() -> None:
    """An active spine accessor must produce a SpineGraphObserver."""
    fake_spine = MagicMock(name="fake_event_spine")
    previous = set_active_spine_accessor(lambda: fake_spine)
    try:
        bindings = _minimal_bindings()
        observer = bindings._build_graph_observer()
    finally:
        set_active_spine_accessor(previous)

    assert isinstance(observer, SpineGraphObserver)

    observer.observe(
        GraphObservation(
            kind=KIND_VISIT_START,
            plan_ref="p1",
            occurred_at_ms=1,
            node_id="a",
        )
    )
    fake_spine.append.assert_called_once()
    call_kwargs = fake_spine.append.call_args.kwargs
    assert call_kwargs["execution_point"] == "phase_graph.node.start"
    payload = call_kwargs["caller_payload"]
    assert payload["kind"] == KIND_VISIT_START
    assert payload["node_id"] == "a"


def test_null_observer_is_distinct_from_spine_observer() -> None:
    """Sanity: the two observer shapes remain distinct types so a
    misconfiguration that returns NullGraphObserver from the wiring
    fails loud instead of silently dropping spine events.
    """
    previous = set_active_spine_accessor(None)
    try:
        bindings = _minimal_bindings()
        assert bindings._build_graph_observer() is None
    finally:
        set_active_spine_accessor(previous)

    assert NullGraphObserver() is not None
