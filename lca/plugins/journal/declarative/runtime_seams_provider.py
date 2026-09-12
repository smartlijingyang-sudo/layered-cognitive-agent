"""Default factories for declaratively selected runtime execution seams.

These factories preserve the existing registry-backed behavior while moving its
concrete construction out of ``DeclarativeRuntimeBindings``.  A profile can
replace any factory capability without changing the runtime kernel.
"""

from __future__ import annotations

from collections.abc import Mapping

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
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols.act.effect.handler import EffectCapabilities, EffectHandlerRegistry
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    DeltaReducer,
    EffectDispatcher,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.journal.artifact.closure import ArtifactClosure
from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyStore
from lca.contracts.protocols.runtime.infra.infra import StateStore
from lca.contracts.protocols.runtime.runtime.composition import (
    CheckpointStateResolver,
    CheckpointStateResolverFactory,
    DeclarativeInterpreter,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectDispatcherFactory,
    ResultFinalizer,
    ResultFinalizerFactory,
    RuntimeJournal,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.runtime.runtime.lifecycle import RuntimeLifecyclePublisher
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.state.reducer import Reducer
from lca.harness.declarative.execute.dispatch import RegistryDeltaReducer, RegistryEffectDispatcher
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.runtime.loop.runtime_journal import RuntimeJournalCommitter
from lca.runtime.projection.result_finalizer import RuntimeResultFinalizer
from lca.runtime.support.checkpoint_resolution import DeclarativeCheckpointStateResolver


class Config(BaseModel):
    """Default declarative runtime-factory configuration."""

    model_config = {"extra": "forbid"}


class RegistryEffectDispatcherFactory(EffectDispatcherFactory):
    """Create the standard policy and idempotency governed effect gateway."""

    def create(
        self,
        *,
        capabilities: EffectCapabilities,
        effect_handler_registry: EffectHandlerRegistry,
        idempotency_store: IdempotencyStore,
    ) -> EffectDispatcher:
        return RegistryEffectDispatcher(
            capabilities,
            effect_handler_registry,
            idempotency_store,
        )


class RegistryDeltaReducerFactory(DeltaReducerFactory):
    """Create the standard registry-dispatched, single-writer delta adapter."""

    def create(
        self,
        *,
        reducer: Reducer,
        delta_handler_registry: DeltaHandlerRegistry,
    ) -> DeltaReducer:
        return RegistryDeltaReducer(reducer, delta_handler_registry)


class DefaultCheckpointStateResolverFactory(CheckpointStateResolverFactory):
    """Create the standard state-store-backed checkpoint resolver."""

    def create(self, *, state_store: StateStore) -> CheckpointStateResolver:
        return DeclarativeCheckpointStateResolver(state_store=state_store)


class DefaultResultFinalizerFactory(ResultFinalizerFactory):
    """Create the standard reducer-driven terminal result finalizer."""

    def create(
        self,
        *,
        reducer: Reducer,
        hooks: HookRegistry,
        artifact_closure: ArtifactClosure,
        state_store: StateStore,
    ) -> ResultFinalizer:
        return RuntimeResultFinalizer(
            reducer=reducer,
            hooks=hooks,
            artifact_closure=artifact_closure,
            state_store=state_store,
        )


class DefaultDeclarativeInterpreterFactory(DeclarativeInterpreterFactory):
    """Build the production interpreter with the five runtime closures.

    After the six-phase subgraph cutover (note 2026-09-12), every
    phase main binds ``subgraph`` and dispatches node executors via
    :class:`NodeExecutorStrategy`. ``PlanInterpreterAdapter`` is the
    sole production interpreter; the adapter carries the runtime
    closures so the subgraph / node_executor strategies can reach
    them when they build per-call views for node plugins.
    """

    def __init__(self) -> None:
        # ADR-0221 P3: ``loop_guard_evaluator`` arg retired; the v2
        # ``PlanInterpreter`` has no loop-guard seam because loop
        # re-entry is owned by the think-phase ``control.think.guard``
        # subgraph node.
        pass

    def create(
        self,
        *,
        journal: RuntimeJournal,
        effect_gateway: EffectDispatcher,
        reducer: DeltaReducer,
        phase_observer: object,
        lifecycle_publisher: RuntimeLifecyclePublisher,
        node_executors: object | None = None,
        node_executor_runtime_scope: object | None = None,
        graph_observer: object | None = None,
        graph_clock: object | None = None,
    ) -> DeclarativeInterpreter:
        # ADR-0221 P3: return the kernel-native ``PlanInterpreter``
        # directly. The runtime-seam strategies are registered inline;
        # the v0 ``PlanInterpreterAdapter`` shim is gone.
        # Build a private registry that mirrors the framework defaults
        # and wires the runtime-seam node-executor lookup into the
        # ``NodeExecutorStrategy`` instance.
        from lca.framework.graph.adapter import default_strategy_registry
        from lca.framework.graph.interpreter import (
            NullGraphObserver,
            PlanInterpreter,
            _default_clock,
        )
        from lca.framework.graph.strategies.node_executor_strategy import (
            NodeExecutorStrategy,
        )
        from lca.framework.graph.strategy_registry import StrategyRegistry

        registry = StrategyRegistry()
        executors_dict: dict[str, object] = {}
        if node_executors is not None and isinstance(node_executors, Mapping):
            executors_dict = dict(node_executors)
        for kind in default_strategy_registry().kinds():
            resolved = default_strategy_registry().resolve(kind)
            if isinstance(resolved, NodeExecutorStrategy):
                # Rebind the runtime-seam ``executor_lookup`` and
                # ``node_runtime_view_factory`` onto the fresh
                # registry so node_executors + agent_state reach the
                # strategy.
                def _view(agent_state, _scope=node_executor_runtime_scope):
                    class _View:
                        __slots__ = ("_scope", "_state")

                        def __init__(self):
                            self._state = agent_state
                            self._scope = _scope

                        @property
                        def state(self):
                            return self._state

                        def __getattr__(self, key):
                            scope = self._scope
                            if scope is None:
                                return None
                            getter = getattr(scope, "get", None) or getattr(scope, "resolve", None)
                            if getter is None:
                                return None
                            try:
                                return getter(key)
                            except (KeyError, AttributeError, TypeError):
                                return None

                    return _View()

                resolved = NodeExecutorStrategy(
                    executor_lookup=lambda *, binding, node_id, region: executors_dict.get(node_id),
                    node_runtime_view_factory=_view,
                )
            registry.register(resolved)

        return PlanInterpreter(
            registry=registry,
            observer=graph_observer or NullGraphObserver(),
            clock=graph_clock or _default_clock,  # store the callable, not the result
        )


class ObservabilityRuntimeJournalFactory(RuntimeJournalFactory):
    """Create one observability-backed journal for each runtime turn."""

    def create(self) -> RuntimeJournal:
        return RuntimeJournalCommitter()


@plugin(
    id="lca-declarative-runtime-seams-provider",
    requires=[],
    provides=[
        "checkpoint_state_resolver_factory",
        "declarative_interpreter_factory",
        "delta_reducer_factory",
        "effect_dispatcher_factory",
        "result_finalizer_factory",
        "runtime_journal_factory",
    ],
    implements=[
        CheckpointStateResolverFactory,
        DeclarativeInterpreterFactory,
        DeltaReducerFactory,
        EffectDispatcherFactory,
        ResultFinalizerFactory,
        RuntimeJournalFactory,
    ],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default checkpoint, terminal, Gateway, DeltaReducer, and per-turn "
        "Journal factories for declarative runtime assembly."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("decision.emit",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-declarative-runtime-seams-provider.checked",
                "lca-declarative-runtime-seams-provider.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(
            "checkpoint_state_resolver_factory",
            "decision.emit",
            "declarative_interpreter_factory",
            "delta_reducer_factory",
            "effect_dispatcher_factory",
            "result_finalizer_factory",
            "runtime_journal_factory",
        ),
        emits=(
            "checkpoint_state_resolver_factory.checked",
            "declarative_interpreter_factory.checked",
            "delta_reducer_factory.checked",
            "effect_dispatcher_factory.checked",
            "result_finalizer_factory.checked",
            "runtime_journal_factory.checked",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register default factory choices as independently replaceable capabilities."""

    del config
    ctx.provide("checkpoint_state_resolver_factory", DefaultCheckpointStateResolverFactory())

    ctx.provide(
        "declarative_interpreter_factory",
        DefaultDeclarativeInterpreterFactory(),
    )
    ctx.provide("delta_reducer_factory", RegistryDeltaReducerFactory())
    ctx.provide("effect_dispatcher_factory", RegistryEffectDispatcherFactory())
    ctx.provide("result_finalizer_factory", DefaultResultFinalizerFactory())
    ctx.provide("runtime_journal_factory", ObservabilityRuntimeJournalFactory())


__all__ = [
    "Config",
    "DefaultCheckpointStateResolverFactory",
    "DefaultDeclarativeInterpreterFactory",
    "DefaultResultFinalizerFactory",
    "ObservabilityRuntimeJournalFactory",
    "RegistryDeltaReducerFactory",
    "RegistryEffectDispatcherFactory",
    "setup",
]
