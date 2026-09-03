import inspect
from dataclasses import replace
from typing import cast
from unittest.mock import MagicMock

import pytest

from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols import (
    ArtifactClosure,
    Body,
    Brain,
    MemorySystem,
    PerceiveHub,
    StateStore,
)
from lca.contracts.protocols.act.effect_handler import EffectHandlerRegistry
from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseExecutor
from lca.contracts.protocols.journal.idempotency import IdempotencyStore
from lca.contracts.protocols.session.resume_input import ResumeInputAdapter
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.contracts.protocols.state.reducer import Reducer
from lca.harness.declarative.lifecycle.phase_observation import PhaseObserver
from lca.plugins.composer.runtime.fixture_runtime_adapter import FixtureRuntimeAdapter
from lca.plugins.composer.runtime.runtime_factory import (
    ProductionRuntimeDeps,
    RuntimeDeps,
    build_cognitive_runtime,
    build_fixture_cognitive_runtime,
)
from lca.plugins.journal.declarative_runtime_seams_provider import (
    DefaultCheckpointStateResolverFactory,
    DefaultDeclarativeInterpreterFactory,
    DefaultResultFinalizerFactory,
    ObservabilityRuntimeJournalFactory,
    RegistryDeltaReducerFactory,
    RegistryEffectDispatcherFactory,
)
from lca.plugins.runtime.reducer import DefaultReducer
from lca.runtime.resume_input import HumanAnswerResumeInputAdapter


def _fixture_deps() -> RuntimeDeps:
    return RuntimeDeps(
        brain=cast("Brain", object()),
        body=cast("Body", object()),
        memory=cast("MemorySystem", object()),
        hooks=cast("HookRegistry", object()),
        state_store=cast("StateStore", object()),
        perceive_hub=cast("PerceiveHub", object()),
        phase_capabilities={},
    )


def _production_deps() -> ProductionRuntimeDeps:
    return ProductionRuntimeDeps(
        brain=cast("Brain", object()),
        body=cast("Body", object()),
        memory=cast("MemorySystem", object()),
        hooks=cast("HookRegistry", object()),
        state_store=cast("StateStore", object()),
        perceive_hub=cast("PerceiveHub", object()),
        reducer=cast("Reducer", DefaultReducer()),
        compiled_plan=cast("CompiledRunPlan", object()),
        phase_executors={},
        phase_capabilities={},
        effect_handler_registry=cast("EffectHandlerRegistry", object()),
        delta_handler_registry=cast("DeltaHandlerRegistry", object()),
        artifact_closure=cast("ArtifactClosure", object()),
        idempotency_store=cast("IdempotencyStore", object()),
        resume_input_adapter=cast("ResumeInputAdapter", HumanAnswerResumeInputAdapter()),
        effect_dispatcher_factory=RegistryEffectDispatcherFactory(),
        delta_reducer_factory=RegistryDeltaReducerFactory(),
        journal_factory=ObservabilityRuntimeJournalFactory(),
        interpreter_factory=DefaultDeclarativeInterpreterFactory(),
        checkpoint_state_resolver_factory=DefaultCheckpointStateResolverFactory(),
        result_finalizer_factory=DefaultResultFinalizerFactory(),
        phase_observer=cast("PhaseObserver", object()),
    )


def test_production_factory_closes_runtime_from_explicit_dependencies() -> None:
    deps = _production_deps()

    runtime = build_cognitive_runtime(deps)

    assert runtime.reducer is deps.reducer
    assert runtime.effect_handler_registry is deps.effect_handler_registry
    assert runtime.delta_handler_registry is deps.delta_handler_registry
    assert runtime.artifact_closure is deps.artifact_closure
    assert runtime.idempotency_store is deps.idempotency_store
    assert runtime.resume_input_adapter is deps.resume_input_adapter
    assert runtime.bindings.effect_dispatcher_factory is deps.effect_dispatcher_factory
    assert runtime.bindings.delta_reducer_factory is deps.delta_reducer_factory
    assert runtime.bindings.journal_factory is deps.journal_factory
    assert (
        runtime.bindings.checkpoint_state_resolver_factory is deps.checkpoint_state_resolver_factory
    )
    assert runtime.bindings.result_finalizer_factory is deps.result_finalizer_factory
    assert runtime.phase_observer is deps.phase_observer
    assert runtime.bindings.plan is deps.compiled_plan
    assert dict(runtime.phase_executors) == {}


def test_production_binding_uses_selected_runtime_mechanism_factories() -> None:
    """Factory selection must be observable from production bindings, not L2 defaults."""

    effect_gateway = object()
    delta_reducer = object()
    journal = object()
    effect_dispatcher_factory = MagicMock()
    effect_dispatcher_factory.create.return_value = effect_gateway
    delta_reducer_factory = MagicMock()
    delta_reducer_factory.create.return_value = delta_reducer
    journal_factory = MagicMock()
    journal_factory.create.return_value = journal
    deps = replace(
        _production_deps(),
        effect_dispatcher_factory=effect_dispatcher_factory,
        delta_reducer_factory=delta_reducer_factory,
        journal_factory=journal_factory,
        checkpoint_state_resolver_factory=MagicMock(),
        result_finalizer_factory=MagicMock(),
    )

    bindings = build_cognitive_runtime(deps).bindings

    assert bindings.new_effect_dispatcher() is effect_gateway
    effect_dispatcher_factory.create.assert_called_once_with(
        capabilities=bindings.capabilities,
        effect_handler_registry=deps.effect_handler_registry,
        idempotency_store=deps.idempotency_store,
    )
    assert bindings.new_delta_reducer() is delta_reducer
    delta_reducer_factory.create.assert_called_once_with(
        reducer=deps.reducer,
        delta_handler_registry=deps.delta_handler_registry,
    )
    assert bindings.journal_factory.create() is journal
    journal_factory.create.assert_called_once_with()


def test_production_binding_uses_selected_recovery_and_terminal_factories() -> None:
    """Checkpoint and terminal choices must be delegated to selected factories."""

    checkpoint_resolver = object()
    result_finalizer = object()
    checkpoint_factory = MagicMock()
    checkpoint_factory.create.return_value = checkpoint_resolver
    finalizer_factory = MagicMock()
    finalizer_factory.create.return_value = result_finalizer
    deps = replace(
        _production_deps(),
        checkpoint_state_resolver_factory=checkpoint_factory,
        result_finalizer_factory=finalizer_factory,
    )
    bindings = build_cognitive_runtime(deps).bindings

    assert bindings.new_checkpoint_state_resolver() is checkpoint_resolver
    checkpoint_factory.create.assert_called_once_with(state_store=deps.state_store)
    assert bindings.new_result_finalizer() is result_finalizer
    finalizer_factory.create.assert_called_once_with(
        reducer=deps.reducer,
        hooks=deps.hooks,
        artifact_closure=deps.artifact_closure,
        state_store=deps.state_store,
    )


def test_production_factory_has_no_ambient_capability_context() -> None:
    """Production closure must be visible in the factory's only argument."""

    assert tuple(inspect.signature(build_cognitive_runtime).parameters) == ("deps",)


def test_production_dependency_model_rejects_missing_closure_member() -> None:
    """Omitting a required production binding fails before runtime construction."""

    with pytest.raises(TypeError, match="artifact_closure"):
        ProductionRuntimeDeps(
            brain=cast("Brain", object()),
            body=cast("Body", object()),
            memory=cast("MemorySystem", object()),
            hooks=cast("HookRegistry", object()),
            state_store=cast("StateStore", object()),
            perceive_hub=cast("PerceiveHub", object()),
            reducer=cast("Reducer", DefaultReducer()),
            compiled_plan=cast("CompiledRunPlan", object()),
            phase_executors=cast("dict[str, PhaseExecutor]", {}),
            phase_capabilities={},
            effect_handler_registry=cast("EffectHandlerRegistry", object()),
            delta_handler_registry=cast("DeltaHandlerRegistry", object()),
            idempotency_store=cast("IdempotencyStore", object()),
            resume_input_adapter=cast("ResumeInputAdapter", HumanAnswerResumeInputAdapter()),
            effect_dispatcher_factory=RegistryEffectDispatcherFactory(),
            delta_reducer_factory=RegistryDeltaReducerFactory(),
            journal_factory=ObservabilityRuntimeJournalFactory(),
            interpreter_factory=DefaultDeclarativeInterpreterFactory(),
            checkpoint_state_resolver_factory=DefaultCheckpointStateResolverFactory(),
            result_finalizer_factory=DefaultResultFinalizerFactory(),
        )


def test_fixture_runtime_does_not_expose_loop_guard_selection_axis() -> None:
    """Loop traversal policy belongs to the interpreter factory, not RuntimeDeps."""

    assert "loop_guard_evaluator" not in RuntimeDeps.__dataclass_fields__
    assert "loop_guard_evaluator" not in inspect.getsource(RuntimeDeps)


def test_fixture_factory_builds_explicit_in_process_binding() -> None:
    runtime = build_fixture_cognitive_runtime(_fixture_deps())

    assert runtime.bindings.effect_handler_registry is not None
    assert runtime.bindings.delta_handler_registry is not None
    assert runtime.bindings.artifact_closure is not None
    assert runtime.bindings.resume_input_adapter is not None
    assert runtime.bindings.effect_dispatcher_factory is not None
    assert runtime.bindings.delta_reducer_factory is not None
    assert runtime.bindings.journal_factory is not None
    assert runtime.bindings.checkpoint_state_resolver_factory is not None
    assert runtime.bindings.result_finalizer_factory is not None


def test_fixture_adapter_owns_defaulting_and_production_translation() -> None:
    """Input data stays passive while one adapter owns fixture adaptation."""

    deps_source = inspect.getsource(RuntimeDeps)
    adapter_source = inspect.getsource(FixtureRuntimeAdapter)
    factory_source = inspect.getsource(build_fixture_cognitive_runtime)

    assert "def with_fixture_defaults(" not in deps_source
    assert "def to_production_runtime_deps(" not in deps_source
    assert "def complete(" in adapter_source
    assert "def to_production_runtime_deps(" in adapter_source
    assert "ProductionRuntimeDeps(" in adapter_source
    assert "FixtureRuntimeAdapter" in factory_source
    assert "ProductionRuntimeDeps(" not in factory_source


def test_fixture_adapter_preserves_explicit_values_when_completing_defaults() -> None:
    """Defaulting must not replace mechanisms explicitly selected by a fixture."""

    sentinel_reducer = DefaultReducer()
    deps = replace(_fixture_deps(), reducer=sentinel_reducer)

    completed = FixtureRuntimeAdapter(deps).complete()

    assert completed.reducer is sentinel_reducer
    assert completed.brain is deps.brain
    assert completed.phase_capabilities["stop_policy"] is completed.stop_policy


def test_binding_freezes_phase_executor_mapping_after_composition() -> None:
    executors: dict[str, PhaseExecutor] = {}
    runtime = build_fixture_cognitive_runtime(replace(_fixture_deps(), phase_executors=executors))

    executors["late"] = cast("PhaseExecutor", object())

    assert "late" not in runtime.phase_executors
