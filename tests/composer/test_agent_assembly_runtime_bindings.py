"""Production Agent assembly must consume declared runtime bindings.

This module protects the recovery-input seam alongside Body and Hook selections.
The State-cluster StopPolicy is a local phase capability, while the production
assembler may resolve a named recovery-input capability without reconstructing
a concrete human-answer adapter.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest

from lca.contracts.capabilities import (
    CHECKPOINT_STATE_RESOLVER_FACTORY,
    DECLARATIVE_INTERPRETER_FACTORY,
    DELTA_REDUCER_FACTORY,
    EFFECT_GATEWAY_FACTORY,
    RESULT_FINALIZER_FACTORY,
    RESUME_INPUT_ADAPTERS,
    RUNTIME_JOURNAL_FACTORY,
    SESSION_LIVE_BUILDER,
    SESSION_PERSISTENCE_FACTORY,
    SESSION_PROJECTION_REGISTRY_FACTORY,
)
from lca.contracts.harness.collaboration.agent import SessionLiveBuilder
from lca.contracts.harness.state.projection import SessionProjectionRegistryFactory
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.contracts.protocols.runtime.runtime_composition import (
    CheckpointStateResolverFactory,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectGatewayFactory,
    ResultFinalizerFactory,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.session.session_persistence import SessionPersistenceFactory
from lca.contracts.protocols.journal.spec import AgentSpec
from lca.harness.profile.boot import boot_profile
from lca.plugins.composer.internal.runtime_binding import (
    ProductionRuntimeDeps,
    bind_runtime_graph,
)
from lca.plugins.composer.internal.runtime_capabilities import RuntimeCapabilityClosure

REPO = Path(__file__).resolve().parents[2]
AGENT_ASSEMBLY_PATH = REPO / "lca" / "plugins" / "composer" / "agent_assembly.py"
RUNTIME_ASSEMBLY_PATH = REPO / "lca" / "plugins" / "composer" / "runtime_assembly.py"
RUNTIME_CAPABILITIES_PATH = (
    REPO / "lca" / "plugins" / "composer" / "internal" / "runtime_capabilities.py"
)
RUNTIME_BINDING_PATH = REPO / "lca" / "plugins" / "composer" / "internal" / "runtime_binding.py"
WEB_APP_BUNDLE_PATH = REPO / "bundles" / "web-app.yaml"


def _read_agent_assembly_source() -> str:
    return AGENT_ASSEMBLY_PATH.read_text(encoding="utf-8")


def _read_runtime_assembly_source() -> str:
    return RUNTIME_ASSEMBLY_PATH.read_text(encoding="utf-8")


def _read_runtime_capabilities_source() -> str:
    return RUNTIME_CAPABILITIES_PATH.read_text(encoding="utf-8")


def _read_runtime_binding_source() -> str:
    return RUNTIME_BINDING_PATH.read_text(encoding="utf-8")


def test_agent_spec_resume_input_adapter_is_overridable() -> None:
    """``AgentSpec`` owns the recovery-input factory key with a stable default."""

    field = AgentSpec.__dataclass_fields__["resume_input_adapter"]
    assert field.default == "human_answer"
    assert field.type == "str"


def test_runtime_binding_adapter_owns_runtime_graph_mapping() -> None:
    """One internal adapter maps graph facts and resolved mechanics to L2 bindings."""

    assembly_source = _read_runtime_assembly_source()
    capabilities_source = _read_runtime_capabilities_source()
    binding_source = _read_runtime_binding_source()

    assert "resolve_runtime_capabilities" in assembly_source
    assert "bind_runtime_graph(" in assembly_source
    assert "ProductionRuntimeDeps" not in assembly_source
    assert "ScopeCapabilityResolver" not in assembly_source
    assert "resolve_phase_executor_bindings" not in assembly_source
    assert "resolve_resume_input_adapter" not in assembly_source

    assert "RESUME_INPUT_ADAPTERS" in capabilities_source
    assert "EFFECT_GATEWAY_FACTORY" in capabilities_source
    assert "DELTA_REDUCER_FACTORY" in capabilities_source
    assert "RUNTIME_JOURNAL_FACTORY" in capabilities_source
    assert "CHECKPOINT_STATE_RESOLVER_FACTORY" in capabilities_source
    assert "DECLARATIVE_INTERPRETER_FACTORY" in capabilities_source
    assert "RESULT_FINALIZER_FACTORY" in capabilities_source
    assert "require_declared_capabilities(" in capabilities_source
    assert "factory: ResumeInputAdapterFactory" in capabilities_source
    assert "adapter_key = spec.resume_input_adapter" in capabilities_source
    assert "factory.create(adapter_key)" in capabilities_source
    assert "RuntimeJournalCommitter" not in capabilities_source
    assert "HumanAnswerResumeInputAdapter" not in capabilities_source
    assert "def from_runtime_graph(" in binding_source
    assert "ProductionRuntimeDeps(" in binding_source
    assert "def from_runtime_graph(" not in inspect.getsource(ProductionRuntimeDeps)
    assert "phase_observer=capabilities.phase_observer" in binding_source
    binder_source = inspect.getsource(bind_runtime_graph)
    assert "from_runtime_graph(" in binder_source
    assert "ProductionRuntimeDeps(" not in binder_source


def test_runtime_binding_adapter_maps_one_complete_graph_to_bindings() -> None:
    """Graph-to-binding field mapping stays local to the internal adapter seam."""

    closure = RuntimeCapabilityClosure(
        reducer=object(),
        effect_handler_registry=object(),
        delta_handler_registry=object(),
        artifact_closure=object(),
        idempotency_store=object(),
        resume_input_adapters=object(),
        phase_observer=object(),
        effect_gateway_factory=object(),
        delta_reducer_factory=object(),
        journal_factory=object(),
        interpreter_factory=object(),
        checkpoint_state_resolver_factory=object(),
        result_finalizer_factory=object(),
        runtime_factory=object(),
        lifecycle_publisher=object(),
    )
    graph = SimpleNamespace(
        brain=object(),
        body=object(),
        memory=object(),
        hooks=object(),
        state_store=object(),
        perceive_hub=object(),
        observability=object(),
        phase_capabilities={"custom": object(), "stop_policy": object()},
    )
    plan = object()
    scope = object()
    spec = cast("AgentSpec", SimpleNamespace())
    resume_input_adapter = object()

    with (
        patch(
            "lca.plugins.composer.internal.runtime_capabilities.resolve_phase_executor_bindings",
            return_value={"execute": object()},
        ) as resolve_executors,
        patch(
            "lca.plugins.composer.internal.runtime_capabilities.resolve_resume_input_adapter",
            return_value=resume_input_adapter,
        ) as resolve_resume_adapter,
    ):
        bindings = bind_runtime_graph(
            closure,
            spec=spec,
            graph=graph,
            plan=cast("CompiledRunPlan", plan),
            scope=scope,
        )

    resolve_executors.assert_called_once_with(plan, scope)
    resolve_resume_adapter.assert_called_once_with(spec, closure.resume_input_adapters)
    assert bindings.reducer is closure.reducer
    assert bindings.effect_handler_registry is closure.effect_handler_registry
    assert bindings.delta_handler_registry is closure.delta_handler_registry
    assert bindings.artifact_closure is closure.artifact_closure
    assert bindings.idempotency_store is closure.idempotency_store
    assert bindings.resume_input_adapter is resume_input_adapter
    assert bindings.capabilities.values == {
        "brain": graph.brain,
        "body": graph.body,
        "memory": graph.memory,
        "perceive_hub": graph.perceive_hub,
        "stop_policy": graph.phase_capabilities["stop_policy"],
        "custom": graph.phase_capabilities["custom"],
    }


def test_production_runtime_deps_rejects_conflicting_phase_capabilities() -> None:
    """Canonical graph facts and executor capabilities must share one owner."""

    brain = object()
    deps = ProductionRuntimeDeps(
        brain=brain,
        body=object(),
        memory=object(),
        hooks=object(),
        state_store=object(),
        perceive_hub=object(),
        reducer=object(),
        compiled_plan=object(),
        phase_executors={},
        phase_capabilities={"brain": object()},
        effect_handler_registry=object(),
        delta_handler_registry=object(),
        artifact_closure=object(),
        idempotency_store=object(),
        resume_input_adapter=object(),
        effect_gateway_factory=object(),
        delta_reducer_factory=object(),
        journal_factory=object(),
        interpreter_factory=object(),
        checkpoint_state_resolver_factory=object(),
        result_finalizer_factory=object(),
        phase_observer=object(),
    )

    with pytest.raises(ValueError, match="phase capability conflicts"):
        deps.runtime_phase_capabilities()


def test_agent_assembly_delegates_runtime_closure_to_the_runtime_seam() -> None:
    """Agent composition must not also own every runtime capability lookup.

    Keeping plan-bound runtime resolution in ``runtime_assembly`` gives the
    runtime closure one test surface and keeps Agent/Team composition local to
    ``PlanBoundAgentAssembler``.
    """

    source = _read_agent_assembly_source()
    assert "assemble_runtime_from_graph(spec, graph, plan=plan, scope=scope)" in source
    assert "ProductionRuntimeDeps" not in source
    assert 'require_capability(scope, "reducer")' not in source
    assert "_phase_executor_bindings" not in source


def test_web_profile_registers_default_resume_input_adapter() -> None:
    """The default production bundle must provide the AgentSpec default key."""

    bundle = WEB_APP_BUNDLE_PATH.read_text(encoding="utf-8")
    assert "id: resume_input.human_answer" in bundle
    assert "$module: lca.plugins.runtime.resume_input" in bundle


def test_booted_web_profile_resolves_human_answer_adapter() -> None:
    """The default profile exposes a working adapter through its registry seam."""

    ctx = asyncio.run(boot_profile("profiles/web-standard.yaml"))
    factory = ctx.inject(RESUME_INPUT_ADAPTERS.key)

    normalized = factory.create("human_answer").normalize("继续")

    assert normalized.input_value == "继续"
    assert normalized.turn is not None
    assert normalized.turn.observation.payload == "继续"


def test_booted_web_profile_resolves_declarative_runtime_factories() -> None:
    """The default bundle exposes all profile-selectable runtime factory seams."""

    ctx = asyncio.run(boot_profile("profiles/web-standard.yaml"))

    assert isinstance(
        ctx.inject(CHECKPOINT_STATE_RESOLVER_FACTORY.key), CheckpointStateResolverFactory
    )
    assert isinstance(ctx.inject(EFFECT_GATEWAY_FACTORY.key), EffectGatewayFactory)
    assert isinstance(ctx.inject(DELTA_REDUCER_FACTORY.key), DeltaReducerFactory)
    assert isinstance(
        ctx.inject(DECLARATIVE_INTERPRETER_FACTORY.key), DeclarativeInterpreterFactory
    )
    assert isinstance(ctx.inject(RESULT_FINALIZER_FACTORY.key), ResultFinalizerFactory)
    assert isinstance(ctx.inject(SESSION_LIVE_BUILDER.key), SessionLiveBuilder)
    assert isinstance(ctx.inject(SESSION_PERSISTENCE_FACTORY.key), SessionPersistenceFactory)
    assert isinstance(
        ctx.inject(SESSION_PROJECTION_REGISTRY_FACTORY.key), SessionProjectionRegistryFactory
    )
    assert isinstance(ctx.inject(RUNTIME_JOURNAL_FACTORY.key), RuntimeJournalFactory)


def test_runtime_phase_capability_projection_is_owned_by_runtime_bindings() -> None:
    """Phase capability projection has one runtime-owned test surface."""

    from lca.runtime.phase_capabilities import project_runtime_phase_capabilities

    brain, body, memory, perceive_hub = object(), object(), object(), object()
    projected = project_runtime_phase_capabilities(
        phase_capabilities={"custom": "declared"},
        brain=brain,
        body=body,
        memory=memory,
        perceive_hub=perceive_hub,
    )

    assert projected.values == {
        "custom": "declared",
        "brain": brain,
        "body": body,
        "memory": memory,
        "perceive_hub": perceive_hub,
    }

    with pytest.raises(ValueError, match="phase capability conflicts"):
        project_runtime_phase_capabilities(
            phase_capabilities={"brain": object()},
            brain=brain,
            body=body,
            memory=memory,
            perceive_hub=perceive_hub,
        )
