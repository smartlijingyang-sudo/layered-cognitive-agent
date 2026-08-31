"""Bind a complete AgentGraph into immutable runtime bindings.

The production dependency value lives in ``runtime_deps``. This module owns
only the binding action: validating graph completeness, resolving plan-selected
inputs, and delegating the final immutable binding construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from lca.contracts.mechanisms import consume
from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseExecutor
from lca.contracts.protocols.session.resume_input import ResumeInputAdapter
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.plugins.composer.runtime.runtime_deps import ProductionRuntimeDeps
from lca.runtime.runtime_bindings import DeclarativeRuntimeBindings

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.harness.composition.composer import AgentGraph
    from lca.contracts.protocols.journal.spec import AgentSpec
    from lca.plugins.composer.runtime.runtime_capabilities import RuntimeCapabilityClosure


def from_runtime_graph(
    *,
    graph: AgentGraph,
    capabilities: RuntimeCapabilityClosure,
    compiled_plan: CompiledRunPlan,
    phase_executors: Mapping[str, PhaseExecutor],
    resume_input_adapter: ResumeInputAdapter,
) -> ProductionRuntimeDeps:
    """Adapt graph facts to the dependency value at the binding seam."""
    return ProductionRuntimeDeps(
        brain=graph.brain,
        body=graph.body,
        memory=consume("memory", graph.memory, from_runtime_graph),
        hooks=graph.hooks,
        state_store=consume("state_store", graph.state_store, from_runtime_graph),
        perceive_hub=graph.perceive_hub,
        reducer=capabilities.reducer,
        compiled_plan=compiled_plan,
        phase_executors=phase_executors,
        phase_capabilities=graph.phase_capabilities,
        effect_handler_registry=capabilities.effect_handler_registry,
        delta_handler_registry=capabilities.delta_handler_registry,
        artifact_closure=capabilities.artifact_closure,
        idempotency_store=capabilities.idempotency_store,
        resume_input_adapter=resume_input_adapter,
        effect_dispatcher_factory=capabilities.effect_dispatcher_factory,
        delta_reducer_factory=capabilities.delta_reducer_factory,
        journal_factory=capabilities.journal_factory,
        interpreter_factory=capabilities.interpreter_factory,
        checkpoint_state_resolver_factory=capabilities.checkpoint_state_resolver_factory,
        result_finalizer_factory=capabilities.result_finalizer_factory,
        phase_observer=capabilities.phase_observer,
        lifecycle_publisher=capabilities.lifecycle_publisher,
    )


def build_production_runtime_bindings(
    deps: ProductionRuntimeDeps,
) -> DeclarativeRuntimeBindings:
    """Freeze one complete production closure before a runtime factory runs."""
    return DeclarativeRuntimeBindings.assemble(
        plan=deps.compiled_plan,
        phase_executors=deps.phase_executors,
        capabilities=deps.runtime_phase_capabilities(),
        reducer=deps.reducer,
        hooks=deps.hooks,
        effect_handler_registry=deps.effect_handler_registry,
        delta_handler_registry=deps.delta_handler_registry,
        artifact_closure=deps.artifact_closure,
        idempotency_store=deps.idempotency_store,
        resume_input_adapter=deps.resume_input_adapter,
        state_store=deps.state_store,
        effect_dispatcher_factory=deps.effect_dispatcher_factory,
        delta_reducer_factory=deps.delta_reducer_factory,
        journal_factory=deps.journal_factory,
        interpreter_factory=deps.interpreter_factory,
        checkpoint_state_resolver_factory=deps.checkpoint_state_resolver_factory,
        result_finalizer_factory=deps.result_finalizer_factory,
        # phase_observer=capabilities.phase_observer remains selected by the closure.
        phase_observer=deps.phase_observer,
        lifecycle_publisher=deps.lifecycle_publisher,
    )


def bind_runtime_graph(
    capabilities: RuntimeCapabilityClosure,
    *,
    spec: AgentSpec,
    graph: AgentGraph,
    plan: CompiledRunPlan,
    scope: Context,
) -> DeclarativeRuntimeBindings:
    """Close one complete graph into immutable runtime bindings at one seam."""
    from lca.plugins.composer.runtime.runtime_capabilities import (
        require_complete_runtime_graph,
        resolve_phase_executor_bindings,
        resolve_resume_input_adapter,
    )

    require_complete_runtime_graph(graph)
    phase_executors = resolve_phase_executor_bindings(plan, scope)
    resume_input_adapter = resolve_resume_input_adapter(
        spec,
        capabilities.resume_input_adapters,
    )
    deps = from_runtime_graph(
        graph=graph,
        capabilities=capabilities,
        compiled_plan=plan,
        phase_executors=phase_executors,
        resume_input_adapter=resume_input_adapter,
    )
    return build_production_runtime_bindings(deps)


__all__ = [
    "ProductionRuntimeDeps",
    "bind_runtime_graph",
    "build_production_runtime_bindings",
    "from_runtime_graph",
]
