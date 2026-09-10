"""Close plan-declared runtime capabilities before runtime construction.

This module owns the mechanics of converting an immutable ``CompiledRunPlan``
and a booted scope into the strongly typed dependencies consumed by the runtime.
Keeping those lookups separate from ``runtime_assembly`` makes the latter a
small orchestration boundary: validate graph, close capabilities, construct.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from lca.contracts.capabilities import (
    CHECKPOINT_STATE_RESOLVER_FACTORY,
    DECLARATIVE_INTERPRETER_FACTORY,
    DELTA_REDUCER_FACTORY,
    EFFECT_DISPATCHER_FACTORY,
    LOOP_GUARD_EVALUATOR,
    PHASE_OBSERVER,
    RESULT_FINALIZER_FACTORY,
    RESUME_INPUT_ADAPTERS,
    RUNTIME_FACTORY,
    RUNTIME_JOURNAL_FACTORY,
    RUNTIME_LIFECYCLE_PUBLISHER,
)
from lca.contracts.mechanisms.capability.capability import MissingCapabilityError
from lca.contracts.protocols.journal.spec.spec import AgentSpec
from lca.contracts.protocols.session.resume.input import (
    ResumeInputAdapter,
    ResumeInputAdapterFactory,
)
from lca.plugins.composer.composition.capability_resolution import (
    CapabilityResolutionError,
    ScopeCapabilityResolver,
)

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.harness.composition.composer import AgentGraph
    from lca.contracts.protocols import ArtifactClosure, Reducer
    from lca.contracts.protocols.act.effect.handler import EffectHandlerRegistry
    from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
        PhaseExecutor,
    )
    from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyStore
    from lca.contracts.protocols.runtime.runtime.composition import (
        CheckpointStateResolverFactory,
        DeclarativeInterpreterFactory,
        DeltaReducerFactory,
        EffectDispatcherFactory,
        ResultFinalizerFactory,
        RuntimeFactory,
        RuntimeJournalFactory,
    )
    from lca.contracts.protocols.runtime.runtime.lifecycle import RuntimeLifecyclePublisher
    from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
    from lca.contracts.protocols.state.plan import CompiledRunPlan
    from lca.harness.declarative.lifecycle.phase_observation import PhaseObserver


_RUNTIME_GRAPH_FIELDS = (
    "brain",
    "body",
    "memory",
    "state_store",
    "perceive_hub",
    "hooks",
    "observability",
)
_RUNTIME_CAPABILITY_KEYS = (
    "artifact_closure",
    CHECKPOINT_STATE_RESOLVER_FACTORY.key,
    DECLARATIVE_INTERPRETER_FACTORY.key,
    DELTA_REDUCER_FACTORY.key,
    "delta_handler_registry",
    EFFECT_DISPATCHER_FACTORY.key,
    "effect_handler_registry",
    LOOP_GUARD_EVALUATOR.key,
    "idempotency_store",
    "llm_resolver",  # ADR-0219 §10.11: optional LLM wire
    PHASE_OBSERVER.key,
    RESULT_FINALIZER_FACTORY.key,
    RUNTIME_FACTORY.key,
    RUNTIME_JOURNAL_FACTORY.key,
    RUNTIME_LIFECYCLE_PUBLISHER.key,
    "reducer",
    RESUME_INPUT_ADAPTERS.key,
)


@dataclass(frozen=True, slots=True)
class RuntimeCapabilityClosure:
    """Plan-declared runtime mechanisms resolved from one booted scope."""

    reducer: Reducer
    effect_handler_registry: EffectHandlerRegistry
    delta_handler_registry: DeltaHandlerRegistry
    artifact_closure: ArtifactClosure
    idempotency_store: IdempotencyStore
    resume_input_adapters: ResumeInputAdapterFactory
    phase_observer: PhaseObserver
    effect_dispatcher_factory: EffectDispatcherFactory
    delta_reducer_factory: DeltaReducerFactory
    journal_factory: RuntimeJournalFactory
    interpreter_factory: DeclarativeInterpreterFactory
    checkpoint_state_resolver_factory: CheckpointStateResolverFactory
    result_finalizer_factory: ResultFinalizerFactory
    runtime_factory: RuntimeFactory
    lifecycle_publisher: RuntimeLifecyclePublisher
    # ADR-0219 §10.11: optional LLM wire the runtime adapter uses to
    # build an LLM-backed think subgraph runtime. ``None`` triggers a
    # fail-loud ``LLMUnavailableError`` from the interpreter factory.
    llm_resolver: object | None = None
    subgraph_resolver: object | None = None


def require_complete_runtime_graph(graph: AgentGraph) -> None:
    """Reject graph gaps before runtime construction obscures their origin."""

    missing = [field for field in _RUNTIME_GRAPH_FIELDS if getattr(graph, field, None) is None]
    if missing:
        raise MissingCapabilityError(
            "plan-bound AgentGraph is incomplete; missing " + ", ".join(missing)
        )


def resolve_runtime_capabilities(
    plan: CompiledRunPlan,
    scope: Context,
) -> RuntimeCapabilityClosure:
    """Close runtime mechanics through the plan-declared provider bindings only."""

    try:
        resolver = ScopeCapabilityResolver.from_scope(scope)
        capabilities = resolver.require_declared_capabilities(
            plan.capability.provider_bindings,
            _RUNTIME_CAPABILITY_KEYS,
        )
    except CapabilityResolutionError as exc:
        raise MissingCapabilityError(f"runtime capability closure failed: {exc}") from exc
    return RuntimeCapabilityClosure(
        reducer=cast("Reducer", capabilities["reducer"]),
        effect_handler_registry=cast(
            "EffectHandlerRegistry", capabilities["effect_handler_registry"]
        ),
        delta_handler_registry=cast("DeltaHandlerRegistry", capabilities["delta_handler_registry"]),
        artifact_closure=cast("ArtifactClosure", capabilities["artifact_closure"]),
        idempotency_store=cast("IdempotencyStore", capabilities["idempotency_store"]),
        resume_input_adapters=cast(
            "ResumeInputAdapterFactory", capabilities[RESUME_INPUT_ADAPTERS.key]
        ),
        phase_observer=cast("PhaseObserver", capabilities[PHASE_OBSERVER.key]),
        effect_dispatcher_factory=cast(
            "EffectDispatcherFactory", capabilities[EFFECT_DISPATCHER_FACTORY.key]
        ),
        delta_reducer_factory=cast("DeltaReducerFactory", capabilities[DELTA_REDUCER_FACTORY.key]),
        journal_factory=cast("RuntimeJournalFactory", capabilities[RUNTIME_JOURNAL_FACTORY.key]),
        interpreter_factory=cast(
            "DeclarativeInterpreterFactory", capabilities[DECLARATIVE_INTERPRETER_FACTORY.key]
        ),
        checkpoint_state_resolver_factory=cast(
            "CheckpointStateResolverFactory",
            capabilities[CHECKPOINT_STATE_RESOLVER_FACTORY.key],
        ),
        result_finalizer_factory=cast(
            "ResultFinalizerFactory", capabilities[RESULT_FINALIZER_FACTORY.key]
        ),
        runtime_factory=cast("RuntimeFactory", capabilities[RUNTIME_FACTORY.key]),
        lifecycle_publisher=cast(
            "RuntimeLifecyclePublisher", capabilities[RUNTIME_LIFECYCLE_PUBLISHER.key]
        ),
        # ADR-0219 §10.11: llm_resolver is optional — Cordis provides it
        # via ``lca-llm-resolver``. If the capability is absent we leave
        # the field ``None``; the interpreter factory raises
        # ``LLMUnavailableError`` when it tries to construct a subgraph
        # runtime without an LLM wire.
        llm_resolver=capabilities.get("llm_resolver"),
        subgraph_resolver=capabilities.get("subgraph_resolver"),
    )


def resolve_resume_input_adapter(
    spec: AgentSpec,
    factory: ResumeInputAdapterFactory,
) -> ResumeInputAdapter:
    """Resolve paused-run semantics through the per-Agent declared registry key."""

    adapter_key = spec.resume_input_adapter
    try:
        adapter = factory.create(adapter_key)
    except KeyError as exc:
        raise MissingCapabilityError(
            f"resume input adapter {adapter_key!r} not registered in {RESUME_INPUT_ADAPTERS.key}"
        ) from exc
    return adapter


def resolve_phase_executor_bindings(
    plan: CompiledRunPlan,
    scope: Context,
    *,
    subgraph_resolver: object | None = None,
) -> dict[str, PhaseExecutor]:
    """Resolve every executor declared by the plan before interpretation starts.

    The graph interpreter receives a closed mapping rather than an ambient
    Context. This preserves plan locality: phase selection is visible from the
    immutable plan and cannot vary later because a Context gained a capability.

    When ``subgraph_resolver`` is provided, bindings from referenced subgraph
    plans are also resolved so that subgraph step executors are available in
    the same scope as outer plan executors.
    """
    from lca.contracts.protocols.state.plan import CompiledRunPlan as _CRP

    capabilities = {
        capability
        for phase_binding in plan.phase_bindings
        for capability in (
            phase_binding.executor_capability,
            *(contribution.executor for contribution in phase_binding.contributions),
        )
    }
    # Walk subgraph_ref edges and collect their bindings too.
    if subgraph_resolver is not None and plan.phase_graph is not None:
        for edge in plan.phase_graph.edges:
            if edge.subgraph_ref is None:
                continue
            sub_plan = subgraph_resolver.resolve(edge.subgraph_ref.plan_ref)
            if not isinstance(sub_plan, _CRP):
                continue
            for sub_binding in sub_plan.phase_bindings:
                capabilities.add(sub_binding.executor_capability)
                for contribution in sub_binding.contributions:
                    capabilities.add(contribution.executor)
    try:
        resolver = ScopeCapabilityResolver.from_scope(scope)
    except CapabilityResolutionError as exc:
        raise MissingCapabilityError("phase executor binding requires a booted Context") from exc
    try:
        bindings = resolver.require_exact_bindings(capabilities)
    except CapabilityResolutionError as exc:
        raise MissingCapabilityError(str(exc)) from exc
    return {
        capability: cast("PhaseExecutor", executor) for capability, executor in bindings.items()
    }


__all__ = [
    "RuntimeCapabilityClosure",
    "require_complete_runtime_graph",
    "resolve_phase_executor_bindings",
    "resolve_resume_input_adapter",
    "resolve_runtime_capabilities",
]
