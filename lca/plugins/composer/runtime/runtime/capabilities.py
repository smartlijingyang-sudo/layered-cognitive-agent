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
    "idempotency_store",
    # ADR-0221 P3: LOOP_GUARD_EVALUATOR retired — loop guard now lives
    # in the think-phase control.think.guard subgraph.
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


def require_complete_runtime_graph(graph: AgentGraph) -> None:
    """Reject graph gaps before runtime construction obscures their origin."""

    missing = [field for field in _RUNTIME_GRAPH_FIELDS if getattr(graph, field, None) is None]
    if missing:
        raise MissingCapabilityError(
            "plan-bound AgentGraph is incomplete; missing " + ", ".join(missing)
        )


def resolve_runtime_capabilities(
    plan: object,
    scope: Context,
) -> RuntimeCapabilityClosure:
    """Close runtime mechanics through the plan-declared provider bindings only.

    ADR-0221 P3: accepts ``V2ExecutablePlan`` and unwraps to its inner
    ``CompiledRunPlan`` before consulting the capability region.
    """
    inner = getattr(plan, "inner", plan)
    try:
        resolver = ScopeCapabilityResolver.from_scope(scope)
        capabilities = resolver.require_declared_capabilities(
            inner.capability.provider_bindings,
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


def resolve_node_executor_bindings(
    scope: Context,
    *,
    composite_separator: str = "::",
    registry_separator: str = "::",
) -> dict[str, "NodeExecutor"]:
    """Collect every node executor the booted scope already published.

    Each think/cognition/concept subgraph node registers its
    :class:`NodeExecutor` under a composite Cordis key
    ``f"{region}::{factory_name}"``. The region prefix varies per
    subgraph (e.g. ``phase:think``, ``concept``); the framework does
    not enumerate them.

    Strategy: walk ``scope.own_bindings`` for any key that ends with
    ``<registry_separator><factory_name>`` where the suffix is a
    non-empty identifier that contains no further separators that
    would indicate a deeper registry nesting. The factory name is the
    last segment after ``registry_separator``; collisions (same factory
    name under different regions) resolve last-writer-wins, which
    matches how Cordis's own resolution order works.

    For a stricter "only top-level subgraph regions" walk, callers can
    pass a custom ``composite_separator`` and pre-filter — but the
    default is deliberately permissive because the framework has no
    business-layer concept of "subgraph region".
    """
    from lca.contracts.protocols.declarative.declarative_1.node_executor import (
        NodeExecutor,
    )
    from lca.harness.plugin.context import collect_context_bindings

    sep = registry_separator
    all_bindings = collect_context_bindings(scope)
    out: dict[str, NodeExecutor] = {}
    for key, value in all_bindings.items():
        if not isinstance(key, str) or sep not in key:
            continue
        factory_name = key.rsplit(sep, 1)[-1]
        if not factory_name or sep in factory_name:
            # ``sep in factory_name`` means the key has a deeper
            # registry nesting we shouldn't flatten.
            continue
        out[factory_name] = cast("NodeExecutor", value)
    return out


__all__ = [
    "RuntimeCapabilityClosure",
    "require_complete_runtime_graph",
    "resolve_node_executor_bindings",
    "resolve_resume_input_adapter",
    "resolve_runtime_capabilities",
]
