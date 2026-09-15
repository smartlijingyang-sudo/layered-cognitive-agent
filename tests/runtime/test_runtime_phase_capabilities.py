"""Tests for the per-run capability injection seam.

``RuntimePhaseCapabilities`` is the closed ``context.runtime.*``
view that think subgraph node executors (``history.derive``,
``llm.call``) resolve declared ports against. Composition populates
the static fields (``brain``, ``body``, ``phase.think.*``, ...).
The per-run ``RunSessionWriter`` and ``LLMAdapter`` are bound
later, so the run loop needs a way to layer them in without
mutating the composition-time closure. These tests pin the
``with_extra`` / ``with_writer`` seams so the fix for the
``writer port must be supplied`` failure mode stays stable.
"""

from __future__ import annotations

from types import SimpleNamespace


from lca.contracts.protocols.act.effect.handler import EffectHandlerRegistry
from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyStore
from lca.contracts.protocols.runtime.runtime.composition import (
    CheckpointStateResolverFactory,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectDispatcherFactory,
    ResultFinalizerFactory,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.session.resume.input import ResumeInputAdapter
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.harness.declarative.lifecycle.phase_observation import PhaseObserver
from lca.runtime.loop.runtime_event_publisher import NullRuntimeLifecyclePublisher
from lca.runtime.support.runtime_bindings import (
    DeclarativeRuntimeBindings,
    RuntimePhaseCapabilities,
)


def _capabilities(**values: object) -> RuntimePhaseCapabilities:
    return RuntimePhaseCapabilities(values)


def test_with_extra_returns_new_instance_with_merged_values() -> None:
    """``with_extra`` returns a fresh instance with the extras layered over."""
    base = _capabilities(brain="B", reasoner="R")
    extra = {"adapter": "A", "writer": "W"}

    layered = base.with_extra(extra)

    assert layered is not base
    assert layered.get("brain") == "B"
    assert layered.get("reasoner") == "R"
    assert layered.get("adapter") == "A"
    assert layered.get("writer") == "W"
    # The original is left alone — frozen.
    assert base.get("adapter") is None
    assert base.get("writer") is None


def test_with_extra_empty_returns_self() -> None:
    """``with_extra({})`` is a no-op; the same instance is returned."""
    base = _capabilities(a=1)
    assert base.with_extra({}) is base


def test_with_writer_returns_bindings_with_writer_in_capabilities() -> None:
    """``DeclarativeRuntimeBindings.with_writer`` exposes the writer on the runtime scope."""
    fake_writer = SimpleNamespace(run_id="run_xyz")
    bindings = _build_bindings()
    assert bindings.capabilities.get("writer") is None

    layered = bindings.with_writer(fake_writer)

    assert layered is not bindings
    assert layered.capabilities.get("writer") is fake_writer
    # Bindings frozen — original writer slot stays empty.
    assert bindings.capabilities.get("writer") is None


def _build_bindings() -> DeclarativeRuntimeBindings:
    return DeclarativeRuntimeBindings.assemble(
        plan=None,
        node_executors={},
        capabilities=_capabilities(brain="B"),
        reducer=SimpleNamespace(name="r"),
        hooks=SimpleNamespace(),
        effect_handler_registry=SimpleNamespace(spec=EffectHandlerRegistry),
        delta_handler_registry=SimpleNamespace(spec=DeltaHandlerRegistry),
        artifact_closure=SimpleNamespace(),
        idempotency_store=SimpleNamespace(spec=IdempotencyStore),
        resume_input_adapter=SimpleNamespace(spec=ResumeInputAdapter),
        state_store=SimpleNamespace(),
        effect_dispatcher_factory=SimpleNamespace(spec=EffectDispatcherFactory),
        delta_reducer_factory=SimpleNamespace(spec=DeltaReducerFactory),
        journal_factory=SimpleNamespace(spec=RuntimeJournalFactory),
        interpreter_factory=SimpleNamespace(spec=DeclarativeInterpreterFactory),
        checkpoint_state_resolver_factory=SimpleNamespace(
            spec=CheckpointStateResolverFactory
        ),
        result_finalizer_factory=SimpleNamespace(spec=ResultFinalizerFactory),
        phase_observer=SimpleNamespace(spec=PhaseObserver),
        lifecycle_publisher=NullRuntimeLifecyclePublisher(),
    )
